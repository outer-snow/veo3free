#!/usr/bin/env python3
"""
图片生成任务控制端 - GUI版本
支持批量任务队列，带进度显示，自动下载图片到output目录
"""

import asyncio
import json
import os
import re
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from datetime import datetime
from pathlib import Path
import threading
import queue
import base64

try:
    from websockets.server import serve
except ImportError:
    print("请安装 websockets: pip install websockets")
    exit(1)

# 创建output目录
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


class TaskManager:
    """任务管理器"""

    def __init__(self):
        self.tasks = []
        self.current_index = 0
        self.is_running = False
        self.clients = set()
        self.pending_results = {}
        self.result_event = asyncio.Event()
        self.current_task_id = None

    def add_tasks(self, prompts):
        """添加批量任务"""
        for prompt in prompts:
            prompt = prompt.strip()
            if prompt:
                task_id = f"task_{len(self.tasks)}_{datetime.now().strftime('%H%M%S%f')}"
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', prompt)[:50]
                filename = f"{len(self.tasks):03d}_{safe_name}.png"
                self.tasks.append({
                    'id': task_id,
                    'prompt': prompt,
                    'status': '等待中',
                    'filename': filename,
                    'url': None
                })
        return len(self.tasks)

    def clear_tasks(self):
        """清空任务列表"""
        self.tasks = []
        self.current_index = 0

    def get_next_task(self):
        """获取下一个待处理任务"""
        while self.current_index < len(self.tasks):
            task = self.tasks[self.current_index]
            if task['status'] == '等待中':
                return task
            self.current_index += 1
        return None


class WebSocketServer:
    """WebSocket服务器"""

    def __init__(self, task_manager, log_callback, update_callback):
        self.task_manager = task_manager
        self.log = log_callback
        self.update_ui = update_callback
        self.server = None
        self.chunk_buffer = {}  # 存储分块数据

    async def handler(self, websocket):
        self.task_manager.clients.add(websocket)
        self.log(f"✅ 客户端已连接，当前连接数: {len(self.task_manager.clients)}")
        self.update_ui()

        try:
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "image_chunk":
                    # 处理分块数据
                    task_id = data.get("task_id")
                    chunk_index = data.get("chunk_index")
                    total_chunks = data.get("total_chunks")
                    chunk_data = data.get("data")

                    if task_id not in self.chunk_buffer:
                        self.chunk_buffer[task_id] = {}

                    self.chunk_buffer[task_id][chunk_index] = chunk_data
                    self.log(f"📥 收到分块 {chunk_index + 1}/{total_chunks}")

                    # 检查是否所有分块都已收到
                    if len(self.chunk_buffer[task_id]) == total_chunks:
                        # 合并所有分块
                        full_base64 = ''.join(
                            self.chunk_buffer[task_id][i]
                            for i in range(total_chunks)
                        )
                        self.task_manager.pending_results[task_id] = {
                            'type': 'base64',
                            'data': full_base64
                        }
                        del self.chunk_buffer[task_id]
                        self.log(f"✅ 分块合并完成，总大小: {len(full_base64) // 1024} KB")
                        self.task_manager.result_event.set()

                elif msg_type == "image_data":
                    # 直接接收完整图片数据
                    task_id = data.get("task_id")
                    image_data = data.get("data")
                    self.log(f"📥 收到图片数据，大小: {len(image_data) // 1024} KB")
                    self.task_manager.pending_results[task_id] = {
                        'type': 'base64',
                        'data': image_data
                    }
                    self.task_manager.result_event.set()

                elif msg_type == "result":
                    task_id = data.get("task_id")
                    url = data.get("url")
                    self.log(f"📥 收到结果: {url[:80]}..." if url and len(url) > 80 else f"📥 收到结果: {url}")
                    self.task_manager.pending_results[task_id] = url
                    self.task_manager.result_event.set()

                elif msg_type == "status":
                    self.log(f"📌 状态: {data.get('message')}")

        except Exception as e:
            self.log(f"连接异常: {e}")
        finally:
            self.task_manager.clients.discard(websocket)
            self.log(f"❌ 客户端断开，当前连接数: {len(self.task_manager.clients)}")
            self.update_ui()

    async def start(self):
        self.server = await serve(
            self.handler,
            "localhost",
            12345,
            max_size=50 * 1024 * 1024  # 增加到 50MB
        )
        self.log("🚀 WebSocket服务器已启动: ws://localhost:12345")

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()


class ImageDownloader:
    """图片下载器"""

    @staticmethod
    async def save_base64_image(base64_data, filename):
        """保存base64图片"""
        filepath = OUTPUT_DIR / filename
        try:
            image_data = base64.b64decode(base64_data)
            with open(filepath, 'wb') as f:
                f.write(image_data)
            return filepath
        except Exception as e:
            print(f"保存图片失败: {e}")
            return None


class Application:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("图片生成任务控制端")
        self.root.geometry("900x700")

        self.task_manager = TaskManager()
        self.msg_queue = queue.Queue()
        self.loop = None
        self.ws_server = None

        self.setup_ui()
        self.start_async_loop()
        self.process_queue()

    def setup_ui(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 状态栏
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_label = ttk.Label(status_frame, text="🔴 服务器未启动")
        self.status_label.pack(side=tk.LEFT)

        self.client_label = ttk.Label(status_frame, text="连接数: 0")
        self.client_label.pack(side=tk.RIGHT)

        # 输入区域
        input_frame = ttk.LabelFrame(main_frame, text="批量输入提示词（每行一个）", padding="5")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.input_text = scrolledtext.ScrolledText(input_frame, height=8, wrap=tk.WORD)
        self.input_text.pack(fill=tk.BOTH, expand=True)

        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_server_btn = ttk.Button(btn_frame, text="启动服务器", command=self.toggle_server)
        self.start_server_btn.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(btn_frame, text="添加任务", command=self.add_tasks).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="从文件导入", command=self.import_from_file).pack(side=tk.LEFT, padx=5)

        self.run_btn = ttk.Button(btn_frame, text="▶ 开始执行", command=self.start_execution)
        self.run_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="⏹ 停止", command=self.stop_execution, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="清空任务", command=self.clear_tasks).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="打开输出目录", command=self.open_output_dir).pack(side=tk.RIGHT)

        # 任务列表
        task_frame = ttk.LabelFrame(main_frame, text="任务队列", padding="5")
        task_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(task_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        self.progress_label = ttk.Label(task_frame, text="0/0 完成")
        self.progress_label.pack()

        # 任务表格
        columns = ('序号', '提示词', '状态', '文件名')
        self.task_tree = ttk.Treeview(task_frame, columns=columns, show='headings', height=8)

        self.task_tree.heading('序号', text='#')
        self.task_tree.heading('提示词', text='提示词')
        self.task_tree.heading('状态', text='状态')
        self.task_tree.heading('文件名', text='文件名')

        self.task_tree.column('序号', width=50, anchor=tk.CENTER)
        self.task_tree.column('提示词', width=400)
        self.task_tree.column('状态', width=100, anchor=tk.CENTER)
        self.task_tree.column('文件名', width=200)

        scrollbar = ttk.Scrollbar(task_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=scrollbar.set)

        self.task_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message):
        """添加日志（线程安全）"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.msg_queue.put(('log', f"[{timestamp}] {message}"))

    def update_ui_from_queue(self):
        """从队列更新UI"""
        self.msg_queue.put(('update_ui', None))

    def process_queue(self):
        """处理消息队列"""
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == 'log':
                    self.log_text.config(state=tk.NORMAL)
                    self.log_text.insert(tk.END, data + "\n")
                    self.log_text.see(tk.END)
                    self.log_text.config(state=tk.DISABLED)
                elif msg_type == 'update_ui':
                    self.refresh_task_list()
                    self.client_label.config(text=f"连接数: {len(self.task_manager.clients)}")
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    def start_async_loop(self):
        """在后台线程启动asyncio事件循环"""

        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        # 等待loop启动
        while self.loop is None:
            pass

    def toggle_server(self):
        """切换服务器状态"""
        if self.ws_server is None:
            asyncio.run_coroutine_threadsafe(self.start_server(), self.loop)
            self.start_server_btn.config(text="停止服务器")
            self.status_label.config(text="🟢 服务器运行中 - ws://localhost:12345")
        else:
            asyncio.run_coroutine_threadsafe(self.stop_server(), self.loop)
            self.start_server_btn.config(text="启动服务器")
            self.status_label.config(text="🔴 服务器未启动")
            self.ws_server = None

    async def start_server(self):
        """启动WebSocket服务器"""
        self.ws_server = WebSocketServer(self.task_manager, self.log, self.update_ui_from_queue)
        await self.ws_server.start()

    async def stop_server(self):
        """停止服务器"""
        if self.ws_server:
            await self.ws_server.stop()
            self.log("服务器已停止")

    def add_tasks(self):
        """从文本框添加任务"""
        text = self.input_text.get("1.0", tk.END)
        prompts = [line.strip() for line in text.strip().split('\n') if line.strip()]
        if prompts:
            count = self.task_manager.add_tasks(prompts)
            self.refresh_task_list()
            self.input_text.delete("1.0", tk.END)
            self.log(f"已添加 {len(prompts)} 个任务，当前共 {count} 个")
        else:
            messagebox.showwarning("提示", "请输入至少一个提示词")

    def import_from_file(self):
        """从文件导入"""
        filepath = filedialog.askopenfilename(
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if filepath:
            with open(filepath, 'r', encoding='utf-8') as f:
                prompts = [line.strip() for line in f if line.strip()]
            if prompts:
                count = self.task_manager.add_tasks(prompts)
                self.refresh_task_list()
                self.log(f"从文件导入 {len(prompts)} 个任务，当前共 {count} 个")

    def refresh_task_list(self):
        """刷新任务列表显示"""
        self.task_tree.delete(*self.task_tree.get_children())

        completed = 0
        for i, task in enumerate(self.task_manager.tasks):
            status = task['status']
            if status == '已完成':
                completed += 1
                tag = 'completed'
            elif status == '处理中':
                tag = 'processing'
            elif status == '失败' or status == '下载失败':
                tag = 'failed'
            elif status == '超时':
                tag = 'timeout'
            else:
                tag = 'pending'

            self.task_tree.insert('', tk.END, values=(
                i + 1,
                task['prompt'][:50] + ('...' if len(task['prompt']) > 50 else ''),
                status,
                task['filename']
            ), tags=(tag,))

        self.task_tree.tag_configure('completed', foreground='green')
        self.task_tree.tag_configure('processing', foreground='blue')
        self.task_tree.tag_configure('failed', foreground='red')
        self.task_tree.tag_configure('timeout', foreground='orange')
        self.task_tree.tag_configure('pending', foreground='gray')

        total = len(self.task_manager.tasks)
        if total > 0:
            self.progress_var.set((completed / total) * 100)
            self.progress_label.config(text=f"{completed}/{total} 完成")
        else:
            self.progress_var.set(0)
            self.progress_label.config(text="0/0 完成")

    def start_execution(self):
        """开始执行任务"""
        if not self.task_manager.clients:
            messagebox.showwarning("提示", "没有连接的客户端，请先在浏览器中打开目标页面")
            return

        if not self.task_manager.tasks:
            messagebox.showwarning("提示", "任务列表为空")
            return

        self.task_manager.is_running = True
        self.run_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        asyncio.run_coroutine_threadsafe(self.execute_tasks(), self.loop)

    def stop_execution(self):
        """停止执行"""
        self.task_manager.is_running = False
        self.run_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.log("⏹ 已停止执行")

    async def execute_tasks(self):
        """执行所有任务"""
        self.log("▶ 开始执行任务队列")

        while self.task_manager.is_running:
            task = self.task_manager.get_next_task()
            if not task:
                self.log("✅ 所有任务已完成")
                break

            if not self.task_manager.clients:
                self.log("⚠️ 客户端已断开，暂停执行")
                break

            # 更新状态为处理中
            task['status'] = '处理中'
            self.update_ui_from_queue()

            self.log(f"📤 发送任务: {task['prompt'][:50]}...")

            # 清除之前的结果
            self.task_manager.result_event.clear()
            self.task_manager.current_task_id = task['id']

            # 发送任务到浏览器
            message = json.dumps({
                'type': 'task',
                'task_id': task['id'],
                'prompt': task['prompt']
            })

            for client in list(self.task_manager.clients):
                try:
                    await client.send(message)
                except Exception as e:
                    self.log(f"发送失败: {e}")

            # 等待结果（最多等待120秒）
            try:
                await asyncio.wait_for(
                    self.task_manager.result_event.wait(),
                    timeout=120.0
                )

                result = self.task_manager.pending_results.get(task['id'])
                if result:
                    # 尝试下载图片
                    saved = await self.download_image(result, task['filename'])
                    if saved:
                        task['status'] = '已完成'
                        task['url'] = str(saved)
                        self.log(f"💾 已保存: {task['filename']}")
                    else:
                        task['status'] = '下载失败'
                        self.log(f"❌ 下载失败: {task['filename']}")
                else:
                    task['status'] = '失败'
                    self.log(f"❌ 未获取到结果")

            except asyncio.TimeoutError:
                task['status'] = '超时'
                self.log(f"⏱️ 任务超时: {task['prompt'][:30]}...")

            self.task_manager.current_index += 1
            self.update_ui_from_queue()

            # 任务间隔
            await asyncio.sleep(2)

        self.msg_queue.put(('log', "任务队列执行结束"))
        # 重置按钮状态
        self.root.after(0, lambda: self.run_btn.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED))

    async def download_image(self, result, filename):
        """下载图片"""
        try:
            if isinstance(result, dict) and result.get('type') == 'base64':
                # Base64数据
                return await ImageDownloader.save_base64_image(result['data'], filename)
            elif isinstance(result, str):
                if result.startswith('data:'):
                    # Data URL
                    base64_data = result.split(',')[1] if ',' in result else result
                    return await ImageDownloader.save_base64_image(base64_data, filename)
                else:
                    self.log(f"⚠️ 不支持的URL格式: {result[:50]}...")
        except Exception as e:
            self.log(f"下载错误: {e}")
        return None

    def clear_tasks(self):
        """清空任务列表"""
        if self.task_manager.is_running:
            messagebox.showwarning("提示", "请先停止执行")
            return
        self.task_manager.clear_tasks()
        self.refresh_task_list()
        self.log("已清空任务列表")

    def open_output_dir(self):
        """打开输出目录"""
        import subprocess
        import platform

        path = str(OUTPUT_DIR.absolute())
        system = platform.system()

        if system == 'Windows':
            os.startfile(path)
        elif system == 'Darwin':  # macOS
            subprocess.run(['open', path])
        else:  # Linux
            subprocess.run(['xdg-open', path])

    def run(self):
        """运行应用"""
        # 自动启动服务器
        self.root.after(500, self.toggle_server)
        self.root.mainloop()


if __name__ == "__main__":
    app = Application()
    app.run()