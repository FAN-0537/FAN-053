# AnythingLLM Webpage

一个零构建依赖的单页控制台，浏览器直接调用本机 **AnythingLLM REST API**：

- 工作区列表与切换（`GET /api/v1/workspaces`）
- 基于工作区对话/检索问答（`POST /api/v1/workspace/{slug}/chat`）
- 上传文档并加入工作区向量化（`POST /api/v1/document/upload` + `update-embeddings`）
- 加载中 / 成功 / 失败三态提示
- 密钥只在运行时由用户输入，保存在 `sessionStorage`，**前端代码中没有任何密钥**
- 所有服务端返回内容使用 `textContent` 渲染，避免 XSS

## 运行

```bash
cd anythingllm-web
python -m http.server 5500
```

浏览器打开 <http://localhost:5500/>。

也可以直接把 `index.html` 拖进浏览器，但建议用本地静态服务器，避免部分浏览器对 `file://` 的 fetch 限制。

## 使用步骤

1. 启动 AnythingLLM 桌面端，确认 `http://localhost:3001` 可访问。
2. 在 AnythingLLM 的 Settings → Developer API 创建 API Key。
3. 页面中填写：
   - API 地址：默认 `http://localhost:3001/api`
   - API Key：刚才创建的密钥
4. 点击「连接并加载工作区」，选择工作区后即可提问或上传文档。

## CORS 说明

浏览器会直接请求 AnythingLLM。若出现 CORS 错误，说明 AnythingLLM 未允许该来源访问。
可选方案：

- 使用 AnythingLLM 桌面版并将其作为同源服务；
- 或在 AnythingLLM 前放置一个允许 `http://localhost:5500` 的反向代理。

本项目不内置代理，避免把密钥放到额外的服务端。

## 安全边界

- 不写死密钥；不把密钥提交到仓库。
- 不把 API 响应直接拼进 `innerHTML`。
- 清除密钥按钮会同时清空 `sessionStorage` 与页面状态。

## 已知限制

- 未实现流式（SSE）输出，回答一次性展示。
- 页面为单工作区上下文；切换工作区会重置多轮会话。
