# 鼠鼠视频下载工具

一个基于 Vue 3 和 FastAPI 的视频解析与下载工具。粘贴视频链接后，可以解析视频信息、选择下载格式、下载视频或提取 MP3 音频。

## 本地开发

需要准备：

- Python 3.11+
- Node.js 20+
- FFmpeg，下载视频和提取音频时需要

### 1. 启动后端

```powershell
cd backend
.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir .\backend --host 127.0.0.1 --port 8000 --reload
```

### 2. 启动前端

另开一个 PowerShell 终端，在项目根目录执行：

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

前端默认地址：

```text
http://127.0.0.1:5173
```

## 环境变量

本地开发一般不需要 `.env`。Docker 或部署时可以复制 `.env.example` 为 `.env` 后按需调整：

- `API_BASE_URL`
- `CORS_ORIGINS`
- `DATA_DIR`
- `DOWNLOAD_DIR`

## Docker Compose

服务器部署推荐使用 Docker Compose。项目默认只把前端暴露到宿主机 `8080` 端口，后端不暴露到宿主机，前端容器会通过 Docker 内部网络访问后端。

Linux 服务器先确认 Docker 服务已启动：

```bash
sudo systemctl enable --now docker
docker --version
docker compose version
```

### 镜像源设置

项目构建阶段已经默认使用国内镜像源：

- 后端 `apt`：清华 Debian 镜像
- 后端 `pip`：清华 PyPI 镜像
- 前端 `npm`：npmmirror 镜像

基础镜像 `python`、`node`、`nginx` 的拉取由 Docker daemon 控制，建议在服务器上配置 Docker Hub registry mirror。替换成你自己的云厂商或内网镜像加速地址后执行：

```bash
DOCKER_REGISTRY_MIRRORS="https://你的-docker-hub-镜像加速地址" sh scripts/setup-docker-registry-mirror.sh
```

如果服务器已有 `/etc/docker/daemon.json`，脚本默认不会覆盖。请手动合并下面这段，或确认可以覆盖后再加 `OVERWRITE_DOCKER_DAEMON_JSON=1`：

```json
{
  "registry-mirrors": [
    "https://你的-docker-hub-镜像加速地址"
  ]
}
```

改完后确认 Docker 已识别镜像源：

```bash
docker info | sed -n '/Registry Mirrors/,+8p'
```

如果你已经把基础镜像同步到私有仓库，也可以复制 `.env.example` 为 `.env` 后替换基础镜像名，例如：

```env
PYTHON_IMAGE=registry.example.com/library/python:3.12-slim
NODE_IMAGE=registry.example.com/library/node:24-alpine
NGINX_IMAGE=registry.example.com/library/nginx:1.27-alpine
```

首次启动：

```powershell
docker compose up -d --build
```

Linux 也可以直接执行：

```bash
sh deploy.sh
```

Windows PowerShell 也可以执行：

```powershell
.\deploy.ps1
```

访问：

- 前端：http://localhost:8080
- 后端健康检查：http://localhost:8080/api/health

查看状态和日志：

```powershell
docker compose ps
docker compose logs -f
```

停止服务：

```powershell
docker compose down
```

如果要修改端口或部署环境变量，复制 `.env.example` 为 `.env` 后调整：

```powershell
Copy-Item .env.example .env
```

常用变量：

- `FRONTEND_PORT`：前端对外端口，默认 `8080`
- `DATA_DIR`：容器内数据目录，默认 `/app/data`
- `DOWNLOAD_DIR`：容器内下载临时目录，默认 `/app/data/downloads`
- `PYTHON_IMAGE` / `NODE_IMAGE` / `NGINX_IMAGE`：基础镜像，可替换为私有仓库或镜像仓库中的同名镜像
- `APT_MIRROR` / `APT_SECURITY_MIRROR`：Debian 软件源镜像
- `PIP_INDEX_URL` / `PIP_TRUSTED_HOST`：Python 包镜像
- `NPM_REGISTRY`：npm 包镜像

如果服务器有防火墙，只需要放行前端端口，例如默认的 `8080`。后端不直接暴露到公网。

如果 `8080` 已被占用或 Docker 没能正常发布该端口，在 `.env` 中改成其他端口后重新启动，例如：

```env
FRONTEND_PORT=18080
```

### Docker Engine 没启动

如果看到类似错误：

```text
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified
```

说明 Docker Desktop 或 Docker daemon 没有启动。

Windows 本机开发：

1. 打开 Docker Desktop，等左下角状态变成 Running。
2. 再执行 `docker compose up -d --build`。

Linux 服务器：

```bash
sudo systemctl enable --now docker
docker compose up -d --build
```

## 当前实现范围

- 视频链接解析
- 抖音专用解析分支
- 下载格式整理
- 视频下载
- MP3 音频提取
- 短期下载票据
- 封面图片代理
