from ErisPulse import sdk
import os
import time
import asyncio
import aiofiles
from typing import Optional
from fastapi import UploadFile, File, Depends, HTTPException, Header, Request
from .video_converter import VideoConverter


class Main:
    def __init__(self):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("EditVideoPlayer")
        self.storage = sdk.storage
        self.converter = VideoConverter()
        
        # 初始化配置
        self._init_config()
        
        # 确保视频目录存在
        if not os.path.exists(self.video_dir):
            os.makedirs(self.video_dir)

        # 注册模块路由
        self._register_routes()

        # 存储活跃会话
        self.active_sessions = {}

        self.logger.info("EditVideoPlayer模块已加载")

    def _init_config(self):
        config = self.sdk.config.getConfig("EditVideoPlayer")
        if not config:
            config = {
                "api_key": "your-secret-api-key",
                "video_directory": "videos",
                "fps": 30,
                "braille_width": 60,
                "braille_height": 30
            }
            self.sdk.config.setConfig("EditVideoPlayer", config)
            self.logger.warning("已创建默认配置，请在 config.toml 中修改 EditVideoPlayer 配置")
        
        self.api_key = config.get("api_key", "your-secret-api-key")
        self.video_dir = config.get("video_directory", "videos")
        self.fps = config.get("fps", 30)
        # 添加新的配置项
        self.braille_width = config.get("braille_width", 60)
        self.braille_height = config.get("braille_height", 30)
        
        # 更新视频转换器的尺寸配置
        self.converter.width = self.braille_width
        self.converter.height = self.braille_height

    @staticmethod
    def should_eager_load():
        return True

    def _get_api_key_dependency(self):
        async def verify_api_key(request: Request, authorization: str = Header(None)):
            client_ip = request.client.host
            if not self.api_key or self.api_key == "your-secret-api-key":
                # 如果没有设置API密钥，则跳过验证
                self.logger.info(f"API访问验证已跳过 (IP: {client_ip})")
                return True
            
            if not authorization:
                self.logger.warning(f"API访问缺少Authorization头 (IP: {client_ip})")
                raise HTTPException(status_code=401, detail="缺少Authorization头")
            
            try:
                scheme, token = authorization.split()
                if scheme.lower() != "bearer":
                    self.logger.warning(f"API访问使用了无效的Authorization方案 (IP: {client_ip})")
                    raise HTTPException(status_code=401, detail="无效的Authorization方案")
                
                if token != self.api_key:
                    self.logger.warning(f"API访问使用了无效的API密钥 (IP: {client_ip})")
                    raise HTTPException(status_code=401, detail="无效的API密钥")
            except ValueError:
                self.logger.warning(f"API访问使用了无效的Authorization格式 (IP: {client_ip})")
                raise HTTPException(status_code=401, detail="无效的Authorization格式")
            
            self.logger.info(f"API访问验证成功 (IP: {client_ip})")
            return True
        
        return verify_api_key

    def _register_routes(self):
        # 创建API密钥依赖
        api_key_dep = self._get_api_key_dependency()

        async def upload_video(
            request: Request,
            file: UploadFile = File(...),
            api_key_valid: bool = Depends(api_key_dep)
        ):
            client_ip = request.client.host
            try:
                file_path = os.path.join(self.video_dir, file.filename)

                # 保存文件
                async with aiofiles.open(file_path, 'wb') as out_file:
                    content = await file.read()
                    await out_file.write(content)

                self.logger.info(f"视频文件已上传: {file.filename} (IP: {client_ip})")
                return {
                    "status": "success",
                    "message": f"视频 {file.filename} 上传成功",
                    "filename": file.filename
                }
            except Exception as e:
                self.logger.error(f"上传视频失败: {str(e)} (IP: {client_ip})")
                return {
                    "status": "error",
                    "message": f"上传失败: {str(e)}"
                }

        async def list_videos(request: Request, api_key_valid: bool = Depends(api_key_dep)):
            client_ip = request.client.host
            try:
                videos = []
                if os.path.exists(self.video_dir):
                    for file in os.listdir(self.video_dir):
                        if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                            file_path = os.path.join(self.video_dir, file)
                            stat = os.stat(file_path)
                            videos.append({
                                "filename": file,
                                "size": stat.st_size,
                                "modified": stat.st_mtime
                            })

                self.logger.info(f"列出视频列表 (IP: {client_ip})")
                return {
                    "status": "success",
                    "videos": videos
                }
            except Exception as e:
                self.logger.error(f"列出视频失败: {str(e)} (IP: {client_ip})")
                return {
                    "status": "error",
                    "message": f"获取视频列表失败: {str(e)}"
                }

        async def play_video(
            request: Request,
            video_name: str, 
            platform: str, 
            target_type: str, 
            target_id: str,
            api_key_valid: bool = Depends(api_key_dep)
        ):
            client_ip = request.client.host
            try:
                # 检查平台是否支持编辑消息
                if not self._is_platform_supported(platform):
                    self.logger.warning(f"平台 {platform} 不支持消息编辑功能 (IP: {client_ip})")
                    return {
                        "status": "error",
                        "message": f"平台 {platform} 不支持消息编辑功能"
                    }

                # 检查视频文件是否存在
                video_path = os.path.join(self.video_dir, video_name)
                if not os.path.exists(video_path):
                    self.logger.warning(f"视频文件 {video_name} 不存在 (IP: {client_ip})")
                    return {
                        "status": "error",
                        "message": f"视频文件 {video_name} 不存在"
                    }

                self.logger.info(f"开始播放视频 {video_name} 在 {platform} 平台 (IP: {client_ip})")
                asyncio.create_task(self._play_video_task(video_path, platform, target_type, target_id))

                return {
                    "status": "success",
                    "message": f"开始播放视频 {video_name} 在 {platform} 平台"
                }
            except Exception as e:
                self.logger.error(f"播放视频失败: {str(e)} (IP: {client_ip})")
                return {
                    "status": "error",
                    "message": f"播放视频失败: {str(e)}"
                }

        self.sdk.router.register_http_route(
            module_name="EditVideoPlayer",
            path="/upload",
            handler=upload_video,
            methods=["POST"]
        )

        self.sdk.router.register_http_route(
            module_name="EditVideoPlayer",
            path="/list",
            handler=list_videos,
            methods=["GET"]
        )

        self.sdk.router.register_http_route(
            module_name="EditVideoPlayer",
            path="/play",
            handler=play_video,
            methods=["POST"]
        )

        @self.sdk.adapter.on("message")
        async def handle_command(data):
            message = data.get("alt_message", "")
            if message.startswith("/video"):
                await self._handle_video_command(data)

        self.logger.info("模块路由注册完成")

    async def _handle_video_command(self, data):
        try:
            platform = data.get("platform")
            detail_type = data.get("detail_type")
            target_id = data.get("group_id") if detail_type == "group" else data.get("user_id")
            target_type = "group" if detail_type == "group" else "user"
            user_id = data.get("user_id", "Unknown")
            
            self.logger.info(f"用户 {user_id} 在 {platform} 平台触发了视频命令")

            message = data.get("alt_message", "").strip()
            parts = message.split()

            if len(parts) < 2:
                self.logger.info(f"用户 {user_id} 请求了视频命令帮助")
                await self.send_message(platform, target_type, target_id, 
                                      "用法: /video <命令> [参数]\n可用命令: list, stop, play <文件名>")
                return

            command = parts[1]

            if command == "list":
                self.logger.info(f"用户 {user_id} 请求列出视频")
                videos = []
                if os.path.exists(self.video_dir):
                    for file in os.listdir(self.video_dir):
                        if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                            videos.append(file)

                if videos:
                    video_list = "\n".join(videos)
                    await self.send_message(platform, target_type, target_id, 
                                          f"可用视频:\n{video_list}")
                else:
                    await self.send_message(platform, target_type, target_id, 
                                          "没有找到可用视频")

            elif command == "play":
                play_command = message[len("/video play "):].strip()
                if not play_command:
                    self.logger.info(f"用户 {user_id} 请求播放视频但未提供文件名")
                    await self.send_message(platform, target_type, target_id, 
                                          "用法: /video play <文件名>")
                    return

                video_name = play_command
                if not self._is_platform_supported(platform):
                    self.logger.warning(f"平台 {platform} 不支持消息编辑功能，用户 {user_id} 尝试播放视频")
                    await self.send_message(platform, target_type, target_id, 
                                          f"平台 {platform} 不支持消息编辑功能")
                    return

                video_path = os.path.join(self.video_dir, video_name)
                if not os.path.exists(video_path):
                    self.logger.warning(f"视频文件 {video_name} 不存在，用户 {user_id} 尝试播放")
                    await self.send_message(platform, target_type, target_id, 
                                          f"视频文件 {video_name} 不存在")
                    return

                self.logger.info(f"用户 {user_id} 开始播放视频: {video_name}")
                asyncio.create_task(self._play_video_task(video_path, platform, target_type, target_id))
                await self.send_message(platform, target_type, target_id, 
                                      f"开始播放视频: {video_name}")
                                      
            elif command == "stop":
                session_key = f"{platform}_{target_type}_{target_id}"
                user_info = f"用户 {user_id}" if target_type == "user" else f"群组 {target_id}"
                
                if session_key in self.active_sessions:
                    # 取消所有正在进行的视频播放任务
                    stopped_count = 0
                    for task in self.active_sessions[session_key]:
                        if not task.done():
                            task.cancel()
                            stopped_count += 1
                    del self.active_sessions[session_key]
                    
                    self.logger.info(f"{user_info} 在 {platform} 平台停止了 {stopped_count} 个视频播放任务")
                    await self.send_message(platform, target_type, target_id, f"已停止所有视频播放 ({stopped_count} 个任务)")
                else:
                    self.logger.info(f"{user_info} 在 {platform} 平台尝试停止视频播放但没有正在播放的视频")
                    await self.send_message(platform, target_type, target_id, "当前没有正在播放的视频")
            else:
                self.logger.warning(f"用户 {user_id} 使用了未知命令: {command}")
                await self.send_message(platform, target_type, target_id, 
                                      "未知命令。可用命令: list, stop, play <文件名>")

        except Exception as e:
            self.logger.error(f"处理视频命令失败: {str(e)}", exc_info=True)
            await self.send_message(platform, target_type, target_id, 
                                  f"处理命令时出错: {str(e)}")

    async def _play_video_task(self, video_path: str, platform: str, target_type: str, target_id: str):
        session_key = f"{platform}_{target_type}_{target_id}"
        user_info = f"用户 {target_id}" if target_type == "user" else f"群组 {target_id}"
        video_name = os.path.basename(video_path)
        
        try:
            adapter = self.sdk.adapter.get(platform)

            # 发送初始消息并正确获取消息ID
            self.logger.info(f"{user_info} 在 {platform} 平台开始播放视频 {video_name}")
            initial_msg_task = adapter.Send.To(target_type, target_id).Text("正在加载视频...")
            initial_msg_result = await initial_msg_task
            
            # 从结果中提取消息ID
            msg_id = None
            if isinstance(initial_msg_result, dict):
                # 如果结果是字典格式
                msg_id = initial_msg_result.get("data", {}).get("message_id") or \
                        initial_msg_result.get("message_id") or \
                        initial_msg_result.get("data", {}).get("messageInfo", {}).get("msgId")
            elif hasattr(initial_msg_result, 'get'):
                # 如果结果有get方法
                msg_id = initial_msg_result.get("data", {}).get("message_id") or \
                        initial_msg_result.get("message_id") or \
                        initial_msg_result.get("data", {}).get("messageInfo", {}).get("msgId")

            if not msg_id:
                self.logger.error(f"无法获取消息ID，无法播放视频 {video_name}。返回结果: {initial_msg_result}")
                # 尝试发送错误消息
                try:
                    await adapter.Send.To(target_type, target_id).Text("播放失败：无法获取消息ID")
                except:
                    pass
                return

            self.logger.debug(f"成功获取消息ID: {msg_id} 用于播放视频 {video_name}")

            # 将当前任务添加到活跃会话中
            current_task = asyncio.current_task()
            if session_key not in self.active_sessions:
                self.active_sessions[session_key] = set()
            self.active_sessions[session_key].add(current_task)

            # 使用视频转换器播放视频
            frame_count = 0
            sleep_time = 1.0 / self.fps if self.fps > 0 else 0.033
            
            async for frame in self.converter.convert_video_to_braille(video_path):
                try:
                    await adapter.Send.To(target_type, target_id).Edit(msg_id, frame)
                    frame_count += 1
                    # 每播放10帧记录一次日志
                    if frame_count % 10 == 0:
                        self.logger.debug(f"视频 {video_name} 已播放 {frame_count} 帧")
                    # 控制播放速度
                    await asyncio.sleep(sleep_time)
                except Exception as e:
                    self.logger.error(f"编辑消息失败: {str(e)} (视频: {video_name})", exc_info=True)
                    break

            # 发送结束消息
            await adapter.Send.To(target_type, target_id).Edit(msg_id, "视频播放结束")
            self.logger.info(f"视频 {video_name} 播放完成，共播放 {frame_count} 帧")
            
            # 播放完成后从活跃会话中移除
            if session_key in self.active_sessions and current_task in self.active_sessions[session_key]:
                self.active_sessions[session_key].remove(current_task)
                if not self.active_sessions[session_key]:  # 如果没有其他任务，删除键
                    del self.active_sessions[session_key]
                    
        except Exception as e:
            self.logger.error(f"播放视频任务失败: {str(e)} (视频: {video_name})", exc_info=True)
            try:
                adapter = self.sdk.adapter.get(platform)
                await adapter.Send.To(target_type, target_id).Text(f"播放视频时出错: {str(e)}")
            except Exception as send_error:
                self.logger.error(f"发送错误消息失败: {str(send_error)}")
            
            # 出错时也从活跃会话中移除
            if session_key in self.active_sessions and current_task in self.active_sessions[session_key]:
                self.active_sessions[session_key].remove(current_task)
                if not self.active_sessions[session_key]:
                    del self.active_sessions[session_key]

    def _is_platform_supported(self, platform: str) -> bool:
        try:
            adapter = self.sdk.adapter.get(platform)
            return hasattr(adapter.Send, 'Edit')
        except Exception as e:
            self.logger.error(f"检查平台支持性时出错: {str(e)}")
            return False

    async def send_message(self, platform: str, target_type: str, target_id: str, message: str):
        try:
            adapter = self.sdk.adapter.get(platform)
            await adapter.Send.To(target_type, target_id).Text(message)
            self.logger.debug(f"向 {platform} 平台的 {target_type} {target_id} 发送消息: {message}")
        except Exception as e:
            self.logger.error(f"发送消息失败: {str(e)}")