from ErisPulse import sdk
import os
import asyncio
import aiofiles
import shlex
from typing import Optional, List, Dict, Any
from fastapi import UploadFile, File, Depends, HTTPException, Header, Request
from .video_converter import VideoConverter
from collections import defaultdict
from datetime import datetime, timedelta


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
        
        # IP上传限制相关属性
        self.ip_upload_limits = defaultdict(list)  # 存储IP上传记录
        self.max_concurrent_uploads_per_ip = 3  # 同一IP最大并发上传数
        self.upload_time_window = 3600  # 1小时内的时间窗口

        self.logger.info("EditVideoPlayer模块已加载")

    def _init_config(self):
        config = self.sdk.config.getConfig("EditVideoPlayer")
        if not config:
            config = {
                "api_key": "your-secret-api-key",   # 访问密钥
                "video_directory": "videos",        # 默认视频目录
                "braille_width": 60,                # 默认 braille 宽度
                "braille_height": 30,               # 默认 braille 高度
                "max_file_size_mb": 50,             # 默认文件上传限制
                "max_concurrent_uploads_per_ip": 3, # 同一IP最大并发上传数
                "max_frame_rate": 10                # 最大帧率
            }
            self.sdk.config.setConfig("EditVideoPlayer", config)
            self.logger.warning("已创建默认配置，请在 config.toml 中修改 EditVideoPlayer 配置")
        
        self.api_key = config.get("api_key", "your-secret-api-key")
        self.video_dir = config.get("video_directory", "videos")

        self.braille_width = config.get("braille_width", 60)
        self.braille_height = config.get("braille_height", 30)
        self.max_frame_rate = config.get("max_frame_rate", 10)
        
        # 文件上传限制配置
        self.max_file_size = config.get("max_file_size_mb", 50) * 1024 * 1024
        self.max_concurrent_uploads_per_ip = config.get("max_concurrent_uploads_per_ip", 3)
        
        # 更新视频转换器的尺寸配置
        self.converter.width = self.braille_width
        self.converter.height = self.braille_height

    @staticmethod
    def should_eager_load() -> bool:
        """
        指定模块是否应立即加载
        
        :return: True 表示应立即加载
        """
        return True

    def _get_api_key_dependency(self):
        """
        创建API密钥验证依赖
        
        :return: 验证函数
        """
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

    def _check_ip_upload_limit(self, client_ip: str) -> bool:
        """
        检查IP上传限制
        
        :param client_ip: 客户端IP地址
        :return: 是否允许上传
        """
        now = datetime.now()
        # 清理1小时前的记录
        self.ip_upload_limits[client_ip] = [
            timestamp for timestamp in self.ip_upload_limits[client_ip]
            if now - timestamp < timedelta(seconds=self.upload_time_window)
        ]
        
        # 检查当前并发上传数
        return len(self.ip_upload_limits[client_ip]) < self.max_concurrent_uploads_per_ip
    
    def _add_ip_upload_record(self, client_ip: str):
        """
        添加IP上传记录
        
        :param client_ip: 客户端IP地址
        """
        self.ip_upload_limits[client_ip].append(datetime.now())
    
    def _remove_ip_upload_record(self, client_ip: str):
        """
        移除IP上传记录
        
        :param client_ip: 客户端IP地址
        """
        if self.ip_upload_limits[client_ip]:
            self.ip_upload_limits[client_ip].pop(0)

    def _get_video_list(self) -> List[Dict[str, Any]]:
        """
        获取视频列表
        
        :return: 视频信息列表
        """
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
        return videos

    def _get_video_by_index(self, index: int) -> Optional[str]:
        """
        根据序号获取视频文件名
        
        :param index: 视频序号（从1开始）
        :return: 视频文件名或None
        """
        videos = self._get_video_list()
        if 1 <= index <= len(videos):
            return videos[index - 1]["filename"]
        return None

    def _is_platform_supported(self, platform: str) -> bool:
        """
        检查平台是否支持消息编辑功能
        
        :param platform: 平台名称
        :return: 是否支持
        """
        try:
            adapter = self.sdk.adapter.get(platform)
            return hasattr(adapter.Send, 'Edit')
        except Exception as e:
            self.logger.error(f"检查平台支持性时出错: {str(e)}")
            return False

    def _register_routes(self):
        # 创建API密钥依赖
        api_key_dep = self._get_api_key_dependency()

        async def upload_video(
            request: Request,
            file: UploadFile = File(...),
            api_key_valid: bool = Depends(api_key_dep)
        ):
            """
            上传视频文件
            
            :param request: HTTP请求对象
            :param file: 上传的文件
            :param api_key_valid: API密钥验证结果
            :return: 上传结果
            """
            client_ip = request.client.host
            try:
                # 检查文件大小
                file_size = 0
                if hasattr(file, 'size'):
                    file_size = file.size
                elif hasattr(file, 'file') and hasattr(file.file, 'seek'):
                    # 获取文件大小
                    pos = file.file.tell()
                    file.file.seek(0, 2)  # 移动到文件末尾
                    file_size = file.file.tell()
                    file.file.seek(pos)  # 恢复原位置
                
                if file_size > self.max_file_size:
                    self.logger.warning(f"文件大小超过限制: {file_size} bytes (IP: {client_ip})")
                    return {
                        "status": "error",
                        "message": f"文件大小超过限制，最大允许 {self.max_file_size // (1024*1024)}MB"
                    }
                
                # 检查并发上传限制
                if not self._check_ip_upload_limit(client_ip):
                    self.logger.warning(f"IP {client_ip} 超过并发上传限制")
                    return {
                        "status": "error",
                        "message": "您有太多文件正在上传，请等待部分上传完成后再试"
                    }
                
                # 记录开始上传
                self._add_ip_upload_record(client_ip)
                
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
                finally:
                    # 移除上传记录
                    self._remove_ip_upload_record(client_ip)
                    
            except Exception as e:
                # 确保即使出错也移除上传记录
                self._remove_ip_upload_record(client_ip)
                self.logger.error(f"上传视频失败: {str(e)} (IP: {client_ip})")
                return {
                    "status": "error",
                    "message": f"上传失败: {str(e)}"
                }

        async def list_videos(request: Request, api_key_valid: bool = Depends(api_key_dep)):
            """
            列出所有视频文件
            
            :param request: HTTP请求对象
            :param api_key_valid: API密钥验证结果
            :return: 视频列表
            """
            client_ip = request.client.host
            try:
                videos = self._get_video_list()

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
            width: int = None,
            height: int = None,
            api_key_valid: bool = Depends(api_key_dep)
        ):
            """
            播放指定视频
            
            :param request: HTTP请求对象
            :param video_name: 视频文件名
            :param platform: 平台名称
            :param target_type: 目标类型
            :param target_id: 目标ID
            :param width: 播放宽度
            :param height: 播放高度
            :param api_key_valid: API密钥验证结果
            :return: 播放结果
            """
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

                self.logger.info(f"开始播放视频 {video_name} 在 {platform} 平台 (尺寸: {width}x{height})")
                asyncio.create_task(self._play_video_task(video_path, platform, target_type, target_id, width, height))

                size_info = f" ({width}x{height})" if width and height else ""
                return {
                    "status": "success",
                    "message": f"开始播放视频 {video_name}{size_info} 在 {platform} 平台"
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
            """
            处理视频播放命令
            
            :param data: 消息数据
            """
            message = data.get("alt_message", "")
            if message.startswith("/video"):
                await self._handle_video_command(data)

        self.logger.info("模块路由注册完成")

    async def _handle_video_command(self, data):
        """
        处理视频命令
        
        :param data: 消息数据
        """
        try:
            platform = data.get("platform")
            detail_type = data.get("detail_type")
            target_id = data.get("group_id") if detail_type == "group" else data.get("user_id")
            target_type = "group" if detail_type == "group" else "user"
            user_id = data.get("user_id", "Unknown")
            
            self.logger.info(f"用户 {user_id} 在 {platform} 平台触发了视频命令")

            message = data.get("alt_message", "").strip()
            
            if message == "/video":
                self.logger.info(f"用户 {user_id} 请求了视频命令帮助")
                await self.send_message(platform, target_type, target_id, 
                                      "用法: /video <命令> [参数]\n"
                                      "可用命令:\n"
                                      "  list - 列出所有可用视频（带序号）\n"
                                      "  stop - 停止当前播放\n"
                                      "  play <文件名或序号> [宽度] [高度] - 播放指定视频\n"
                                      "提示：可以使用 /video list 查看视频列表和对应序号")
                return

            # 使用 shlex.split 来正确处理引号
            try:
                parts = shlex.split(message)
            except ValueError as e:
                await self.send_message(platform, target_type, target_id, 
                                      "命令格式错误，请检查引号是否匹配")
                return

            if len(parts) < 2:
                self.logger.info(f"用户 {user_id} 请求了视频命令帮助")
                await self.send_message(platform, target_type, target_id, 
                                      "用法: /video <命令> [参数]\n"
                                      "可用命令:\n"
                                      "  list - 列出所有可用视频（带序号）\n"
                                      "  stop - 停止当前播放\n"
                                      "  play <文件名或序号> [宽度] [高度] - 播放指定视频\n"
                                      "提示：可以使用 /video list 查看视频列表和对应序号")
                return

            command = parts[1]

            if command == "list":
                self.logger.info(f"用户 {user_id} 请求列出视频")
                videos = self._get_video_list()
                
                if videos:
                    video_list_items = []
                    for i, video in enumerate(videos, 1):
                        video_list_items.append(f"{i}. {video['filename']}")
                    video_list = "\n".join(video_list_items)
                    await self.send_message(platform, target_type, target_id, 
                                          f"可用视频:\n{video_list}")
                else:
                    await self.send_message(platform, target_type, target_id, 
                                          "没有找到可用视频")

            elif command == "play":
                if len(parts) < 3:
                    self.logger.info(f"用户 {user_id} 请求播放视频但未提供文件名或序号")
                    await self.send_message(platform, target_type, target_id, 
                                          "用法: /video play <文件名或序号> [宽度] [高度]\n"
                                          "提示：文件名如果有空格，需要用引号包裹")
                    return

                # 获取视频标识（文件名或序号）
                video_identifier = parts[2]
                video_name = None
                
                # 判断是序号还是文件名
                if video_identifier.isdigit():
                    # 是数字，尝试作为序号处理
                    index = int(video_identifier)
                    video_name = self._get_video_by_index(index)
                    if not video_name:
                        await self.send_message(platform, target_type, target_id, 
                                              f"无效的视频序号: {index}，请使用 /video list 查看可用视频")
                        return
                else:
                    # 不是数字，作为文件名处理
                    video_name = video_identifier
                    # 检查文件是否存在
                    video_path = os.path.join(self.video_dir, video_name)
                    if not os.path.exists(video_path):
                        self.logger.warning(f"视频文件 {video_name} 不存在，用户 {user_id} 尝试播放")
                        await self.send_message(platform, target_type, target_id, 
                                              f"视频文件 {video_name} 不存在")
                        return

                # 解析可选的宽度和高度参数
                width = None
                height = None
                if len(parts) >= 5:
                    try:
                        width = int(parts[3])
                        height = int(parts[4])
                        # 限制尺寸范围，防止过大
                        width = max(10, min(width, 100))
                        height = max(5, min(height, 50))
                    except ValueError:
                        await self.send_message(platform, target_type, target_id, 
                                              "宽度和高度必须是数字")
                        return

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

                self.logger.info(f"用户 {user_id} 开始播放视频: {video_name} (尺寸: {width}x{height})")
                # 传递宽度和高度参数
                asyncio.create_task(self._play_video_task(video_path, platform, target_type, target_id, width, height))
                size_info = f" ({width}x{height})" if width and height else ""
                await self.send_message(platform, target_type, target_id, 
                                      f"开始播放视频: {video_name}{size_info}")
                                      
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
                                      "未知命令。可用命令:\n"
                                      "  list - 列出所有可用视频（带序号）\n"
                                      "  stop - 停止当前播放\n"
                                      "  play <文件名或序号> [宽度] [高度] - 播放指定视频")

        except Exception as e:
            self.logger.error(f"处理视频命令失败: {str(e)}", exc_info=True)
            await self.send_message(platform, target_type, target_id, 
                                  f"处理命令时出错: {str(e)}")

    async def _play_video_task(self, video_path: str, platform: str, target_type: str, target_id: str, 
                               width: int = None, height: int = None):
        """
        视频播放任务
        
        :param video_path: 视频文件路径
        :param platform: 平台名称
        :param target_type: 目标类型
        :param target_id: 目标ID
        :param width: 播放宽度
        :param height: 播放高度
        """
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
                    adapter.Send.To(target_type, target_id).Text("播放失败：无法获取消息ID")
                except:
                    pass
                return

            self.logger.debug(f"成功获取消息ID: {msg_id} 用于播放视频 {video_name}")

            # 将当前任务添加到活跃会话中
            current_task = asyncio.current_task()
            if session_key not in self.active_sessions:
                self.active_sessions[session_key] = set()
            self.active_sessions[session_key].add(current_task)

            # 保存原始尺寸设置
            original_width = self.converter.width
            original_height = self.converter.height
            
            # 如果用户指定了尺寸，则临时修改
            if width and height:
                self.converter.width = width
                self.converter.height = height

            # 获取视频帧率
            video_fps, _a, _b = self.converter.get_video_info(video_path)
            self.logger.info(f"视频 {video_name} 的帧率为 {video_fps} FPS")
            
            # 计算发送帧间隔
            send_fps = min(video_fps, self.max_frame_rate)
            sleep_time = 1.0 / send_fps
            
            self.logger.info(f"将以 {send_fps} FPS 的速度播放视频（原始帧率 {video_fps} FPS）")

            # 使用视频转换器播放视频
            frame_count = 0
            last_frame_content = None  # 记录上一帧内容
            
            async for frame in self.converter.convert_video_to_braille(video_path):
                try:
                    # 只有当帧内容不同时才发送
                    if frame != last_frame_content:
                        adapter.Send.To(target_type, target_id).Edit(msg_id, frame)
                        last_frame_content = frame
                        frame_count += 1
                        # 每播放10帧记录一次日志
                        if frame_count % 10 == 0:
                            self.logger.debug(f"视频 {video_name} 已播放 {frame_count} 帧")
                    else:
                        self.logger.debug(f"跳过发送重复帧 {frame_count}")
                    
                    # 控制播放速度
                    await asyncio.sleep(sleep_time)
                except Exception as e:
                    self.logger.error(f"编辑消息失败: {str(e)} (视频: {video_name})", exc_info=True)
                    break

            # 恢复原始尺寸设置
            if width and height:
                self.converter.width = original_width
                self.converter.height = original_height

            # 发送结束消息
            adapter.Send.To(target_type, target_id).Edit(msg_id, "视频播放结束")
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
                adapter.Send.To(target_type, target_id).Text(f"播放视频时出错: {str(e)}")
            except Exception as send_error:
                self.logger.error(f"发送错误消息失败: {str(send_error)}")
            
            # 出错时也从活跃会话中移除
            if session_key in self.active_sessions and current_task in self.active_sessions[session_key]:
                self.active_sessions[session_key].remove(current_task)
                if not self.active_sessions[session_key]:
                    del self.active_sessions[session_key]

    async def send_message(self, platform: str, target_type: str, target_id: str, message: str):
        """
        发送消息
        
        :param platform: 平台名称
        :param target_type: 目标类型
        :param target_id: 目标ID
        :param message: 消息内容
        """
        try:
            adapter = self.sdk.adapter.get(platform)
            adapter.Send.To(target_type, target_id).Text(message)
            self.logger.debug(f"向 {platform} 平台的 {target_type} {target_id} 发送消息: {message}")
        except Exception as e:
            self.logger.error(f"发送消息失败: {str(e)}")