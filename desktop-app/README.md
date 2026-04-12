# 校园学习助手（桌面客户端）

快速说明：这是一个基于 Electron + Vite + React 的最小桌面客户端示例，直接对接现有后端 `http://127.0.0.1:8000` 的 `/chat` 与 `/materials` 接口。

快速开始：

1. 进入目录并安装依赖：

```bash
cd desktop-app
npm install
```

2. 本地开发：先启动后端（确保 `server.py` 在运行，默认端口 8000），然后运行：

```bash
npm run dev
```

3. 打包：

```bash
npm run build
npm run start
```

说明（简明）：
- 前端默认后端地址可以在界面设置，或通过环境变量 `BACKEND_URL` 注入。
- 聊天调用使用 `POST /chat`，请求体与后端一致（`user_id`、`session_id`、`messages`、`use_retrieval`）。
- 资料上传使用 `POST /materials/upload`，以 `multipart/form-data` 方式发送 `course_id`、`title`、`file`。

文件说明：
- `main.js`：Electron 主进程（窗口创建、dev/prod 加载）。
- `preload.js`：将 `BACKEND_URL` 暴露给渲染进程（安全隔离）。
- `src/`：React 源码，`App.jsx` 为主 UI，`api.js` 为后端调用封装。
