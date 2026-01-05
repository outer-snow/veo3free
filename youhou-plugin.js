// ==UserScript==
// @name         图片生成 WebSocket 客户端 (增强版)
// @namespace    http://tampermonkey.net/
// @version      2.1
// @match        *://*/*
// @grant        none
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    if (window.self !== window.top) return;

    let capturedImageData = null;  // 存储已转换的base64数据
    let onImageCaptured = null;
    let currentTaskId = null;

    // Blob URL 转 Base64（立即执行）
    async function blobUrlToBase64(blobUrl) {
        try {
            const response = await fetch(blobUrl);
            const blob = await response.blob();
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => {
                    const base64 = reader.result.split(',')[1];
                    console.log('✅ Base64转换成功，大小:', Math.round(base64.length / 1024), 'KB');
                    resolve(base64);
                };
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
        } catch (e) {
            console.error('❌ 转换失败:', e);
            return null;
        }
    }

    // 拦截 URL.createObjectURL，在创建时立即转换
    const origCreateObjectURL = URL.createObjectURL.bind(URL);
    URL.createObjectURL = function(blob) {
        const url = origCreateObjectURL(blob);

        // 检查是否是图片
        if (blob && (blob.type?.startsWith('image/') || blob.size > 100000)) {
            console.log('📥 拦截到 Blob:', blob.type, '大小:', Math.round(blob.size / 1024), 'KB');

            // 立即转换为base64
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64 = reader.result.split(',')[1];
                capturedImageData = base64;
                console.log('✅ 已缓存Base64数据');
                if (onImageCaptured) onImageCaptured(base64);
            };
            reader.readAsDataURL(blob);
        }

        return url;
    };

    // 同时也拦截 createElement 作为备用
    const origCreate = document.createElement.bind(document);
    document.createElement = function(tag) {
        const el = origCreate(tag);
        if (tag.toLowerCase() === 'a') {
            let _href = '';
            Object.defineProperty(el, 'href', {
                get() { return _href; },
                set(v) {
                    _href = v;
                    if (v && v.includes('blob:')) {
                        console.log('📥 a标签拦截到:', v);
                        // 尝试立即获取（可能已经太晚了，但试一下）
                        if (!capturedImageData) {
                            blobUrlToBase64(v).then(data => {
                                if (data) {
                                    capturedImageData = data;
                                    if (onImageCaptured) onImageCaptured(data);
                                }
                            });
                        }
                    }
                    el.setAttribute('href', v);
                }
            });
        }
        return el;
    };

    // 等待图片数据
    function waitForImageData(timeout = 45000) {
        return new Promise((resolve) => {
            if (capturedImageData) {
                const data = capturedImageData;
                capturedImageData = null;
                resolve(data);
                return;
            }

            const timer = setTimeout(() => {
                onImageCaptured = null;
                resolve(null);
            }, timeout);

            onImageCaptured = (data) => {
                clearTimeout(timer);
                onImageCaptured = null;
                capturedImageData = null;
                resolve(data);
            };
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    function init() {
        const $x1 = (xpath, target=document) => document.evaluate(xpath, target, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        const sleep = ms => new Promise(r => setTimeout(r, ms));

        let ws = null;
        let isExecuting = false;

        async function executeTask(taskId, prompt) {
            if (isExecuting) return;
            isExecuting = true;
            capturedImageData = null;  // 清除之前的缓存
            currentTaskId = taskId;

            try {



                sendStatus('设置参数中');
                // 设置参数
                // 1. 打开参数面板
                $x1('//textarea[@id="PINHOLE_TEXT_AREA_ELEMENT_ID"]/..//button[contains(., "Settings")]').click()

                // 2.1 分辨率设置：
                await sleep(300);
                $x1('//button[contains(., "Aspect Ratio")]').click()
                await sleep(300);
                $x1('//div[@role="option"]//span[contains(text(), "16:9")]').click()

                // 2.2 输出数量设置，这里只支持1，如果要修改需要从代码中改
                await sleep(300);
                $x1('//button[contains(., "Outputs per prompt")]').click()
                await sleep(300);
                $x1('//div[@role="option" and normalize-space()="1"]').click()


                sendStatus('开始: ' + prompt);

                const input = $x1('//textarea[@id="PINHOLE_TEXT_AREA_ELEMENT_ID"]');
                if (!input) {
                    sendStatus('未找到输入框');
                    sendResult(taskId, null, '未找到输入框');
                    return;
                }

                input.click();
                await sleep(300);
                input.focus();
                document.execCommand('selectAll');
                document.execCommand('insertText', false, prompt);

                await sleep(300);
                const submitBtn = $x1('//textarea[@id="PINHOLE_TEXT_AREA_ELEMENT_ID"]//following-sibling::div/div[last()]//button');
                if (submitBtn) {
                    submitBtn.click();
                    sendStatus('等待生成...');
                }

                // 等待生成完成
                for (let i = 0; i < 20; i++) {
                    await sleep(3000);



                    const processText = $x1('//div[@data-item-index][contains(., "Reuse prompt")]/div/div/div/div/div[1]').innerText;

                    if (processText.trim().endsWith('%')) {
                        console.log('进度', processText)
                        sendStatus('生成中，进度 ' + processText);
                    } else {
                        if (processText.indexOf('\n') > -1) {
                            // 这种情况，得到的innerText内容包含换行，比如'prompt_suggestion\nAdd To Prompt'
                            sendStatus('生成成功');
                            break;
                        } else {
                            // 单行，且没有了进度符号，说明失败了。
                            throw new Error(`生成失败: ${processText}`);
                        }
                    }
                }


                // 点击下载按钮
                // 注意，这里放弃了根据内容去查找任务容器的方案，而是直接用第一个容器，因为任务容器在生成完成前后，并不是同一个元素
                const taskContainerEl = $x1('//div[@data-item-index][contains(., "Reuse prompt")]/div/div/div/div')
                console.log("taskContainerEl2", taskContainerEl)
                const dlBtn = $x1(`//button[.//*[contains(text(),'download')]]`, taskContainerEl);
                console.log("dlBtn", dlBtn)
                sendStatus('尝试下载...');
                if (dlBtn) {
                    dlBtn.click();
                    await sleep(500);
                }

                const dl4k = $x1("//*[contains(text(), 'Download 4K')]");
                if (dl4k) {
                    sendStatus('点击 Download 4K...');
                    dl4k.click();
                }

                // 等待图片数据（在点击下载后，createObjectURL会被调用）
                sendStatus('等待图片数据...');
                const base64Data = await waitForImageData(45000);

                if (base64Data) {
                    sendStatus('发送图片数据...');

                    // 分块发送大文件
                    const chunkSize = 1024 * 1024;  // 1MB per chunk
                    const totalChunks = Math.ceil(base64Data.length / chunkSize);

                    if (totalChunks > 1) {
                        sendStatus(`图片较大，分${totalChunks}块发送...`);
                        for (let i = 0; i < totalChunks; i++) {
                            const chunk = base64Data.slice(i * chunkSize, (i + 1) * chunkSize);
                            ws.send(JSON.stringify({
                                type: 'image_chunk',
                                task_id: taskId,
                                chunk_index: i,
                                total_chunks: totalChunks,
                                data: chunk
                            }));
                            await sleep(100);  // 避免发送过快
                        }
                    } else {
                        ws.send(JSON.stringify({
                            type: 'image_data',
                            task_id: taskId,
                            data: base64Data
                        }));
                    }

                    sendStatus('图片数据已发送 ✅');
                } else {
                    sendResult(taskId, null, '未获取到图片数据');
                }

            } catch (e) {
                console.error('执行错误:', e);
                sendResult(taskId, null, e.message);
            } finally {
                isExecuting = false;
            }
        }

        function sendResult(taskId, url, error = null) {
            if (ws?.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'result',
                    task_id: taskId,
                    url: url || error || '未获取到链接'
                }));
            }
        }

        function sendStatus(msg) {
            console.log('📌', msg);
            if (ws?.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'status', message: msg }));
            }
        }

        function connect() {
            ws = new WebSocket('ws://localhost:12345');
            ws.onopen = () => updateButton('已连接', '#28a745');
            ws.onmessage = async (e) => {
                const data = JSON.parse(e.data);
                if (data.type === 'task') {
                    await executeTask(data.task_id, data.prompt);
                }
            };
            ws.onclose = () => {
                updateButton('已断开', '#dc3545');
                setTimeout(connect, 3000);
            };
            ws.onerror = () => {};
        }

        const btn = document.createElement('div');
        btn.textContent = '连接中...';
        btn.style.cssText = `position:fixed;bottom:20px;right:20px;z-index:99999;padding:10px 20px;background:#6c757d;color:white;border-radius:5px;cursor:pointer;font-family:sans-serif;font-size:14px;box-shadow:0 2px 10px rgba(0,0,0,0.2);`;
        btn.onclick = () => ws?.readyState === WebSocket.OPEN ? ws.close() : connect();
        document.body.appendChild(btn);

        function updateButton(text, color) {
            btn.textContent = text;
            btn.style.background = color;
        }

        connect();
    }
})();