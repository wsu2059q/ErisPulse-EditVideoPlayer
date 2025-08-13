# ErisPulse-EditVideoPlayer

一个通用的视频播放器模块，可将视频转换为点阵字符并在支持消息编辑的平台上播放。

## 功能特性

- 上传和管理视频文件
- 将视频转换为盲文点阵字符
- 在支持消息编辑的平台上播放视频
- 支持命令行和 HTTP API 控制
- 自适应移动端显示比例

## 安装

使用 ErisPulse CLI 安装模块：

```bash
epsdk install EditVideoPlayer
```

## 配置

在 `config.toml` 中配置模块：

```toml
[EditVideoPlayer]
api_key = "your-secret-api-key"     # API密钥，用于保护HTTP接口
video_directory = "videos"          # 视频存储目录
fps = 30                            # 默认播放帧率
braille_width = 60                  # 盲文字符宽度(字符数)
braille_height = 30                 # 盲文字符高度(字符数)
```

首次运行时会自动创建默认配置。

## 使用方法

### 命令控制

```
/video list              # 列出所有可用视频
/video play <文件名>     # 播放指定视频
/video stop              # 停止当前播放的视频
```

### HTTP API

所有API端点都需要在请求头中添加认证信息（如果配置了api_key）：
```
Authorization: Bearer your-secret-api-key
```

#### 上传视频
```
POST /EditVideoPlayer/upload
Headers: Authorization: Bearer your-secret-api-key
Content-Type: multipart/form-data

参数:
- file: 要上传的视频文件

返回:
{
  "status": "success|error",
  "message": "操作结果信息",
  "filename": "文件名" (仅成功时)
}
```

#### 列出视频
```
GET /EditVideoPlayer/list
Headers: Authorization: Bearer your-secret-api-key

返回:
{
  "status": "success|error",
  "videos": [
    {
      "filename": "文件名",
      "size": 文件大小(字节),
      "modified": 最后修改时间(时间戳)
    }
  ] (仅成功时)
}
```

#### 播放视频
```
POST /EditVideoPlayer/play
Headers: Authorization: Bearer your-secret-api-key
Content-Type: application/json

参数:
{
  "video_name": "要播放的视频文件名",
  "platform": "平台名称",
  "target_type": "目标类型（user/group）",
  "target_id": "目标ID"
}

返回:
{
  "status": "success|error",
  "message": "操作结果信息"
}
```

## 故障排除

### 视频播放失败
- 检查平台是否支持消息编辑
- 确认视频文件存在且格式正确（mp4, avi, mov, mkv）
- 查看日志获取详细错误信息

### 文件上传问题
- 检查服务器磁盘空间
- 验证文件大小限制
