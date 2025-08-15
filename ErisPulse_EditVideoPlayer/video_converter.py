import cv2
import asyncio
import numpy as np
from typing import AsyncGenerator, Tuple

class VideoConverter:
    def __init__(self, width: int = 60, height: int = 30):
        self.width = width
        self.height = height
        self.braille_chars = np.array([
            '⠀', '⠁', '⠂', '⠃', '⠄', '⠅', '⠆', '⠇',
            '⠈', '⠉', '⠊', '⠋', '⠌', '⠍', '⠎', '⠏',
            '⠐', '⠑', '⠒', '⠓', '⠔', '⠕', '⠖', '⠗',
            '⠘', '⠙', '⠚', '⠛', '⠜', '⠝', '⠞', '⠟',
            '⠠', '⠡', '⠢', '⠣', '⠤', '⠥', '⠦', '⠧',
            '⠨', '⠩', '⠪', '⠫', '⠬', '⠭', '⠮', '⠯',
            '⠰', '⠱', '⠲', '⠳', '⠴', '⠵', '⠶', '⠷',
            '⠸', '⠹', '⠺', '⠻', '⠼', '⠽', '⠾', '⠿',
            '⡀', '⡁', '⡂', '⡃', '⡄', '⡅', '⡆', '⡇',
            '⡈', '⡉', '⡊', '⡋', '⡌', '⡍', '⡎', '⡏',
            '⡐', '⡑', '⡒', '⡓', '⡔', '⡕', '⡖', '⡗',
            '⡘', '⡙', '⡚', '⡛', '⡜', '⡝', '⡞', '⡟',
            '⡠', '⡡', '⡢', '⡣', '⡤', '⡥', '⡦', '⡧',
            '⡨', '⡩', '⡪', '⡫', '⡬', '⡭', '⡮', '⡯',
            '⡰', '⡱', '⡲', '⡳', '⡴', '⡵', '⡶', '⡷',
            '⡸', '⡹', '⡺', '⡻', '⡼', '⡽', '⡾', '⡿',
            '⢀', '⢁', '⢂', '⢃', '⢄', '⢅', '⢆', '⢇',
            '⢈', '⢉', '⢊', '⢋', '⢌', '⢍', '⢎', '⢏',
            '⢐', '⢑', '⢒', '⢓', '⢔', '⢕', '⢖', '⢗',
            '⢘', '⢙', '⢚', '⢛', '⢜', '⢝', '⢞', '⢟',
            '⢠', '⢡', '⢢', '⢣', '⢤', '⢥', '⢦', '⢧',
            '⢨', '⢩', '⢪', '⢫', '⢬', '⢭', '⢮', '⢯',
            '⢰', '⢱', '⢲', '⢳', '⢴', '⢵', '⢶', '⢷',
            '⢸', '⢹', '⢺', '⢻', '⢼', '⢽', '⢾', '⢿',
            '⣀', '⣁', '⣂', '⣃', '⣄', '⣅', '⣆', '⣇',
            '⣈', '⣉', '⣊', '⣋', '⣌', '⣍', '⣎', '⣏',
            '⣐', '⣑', '⣒', '⣓', '⣔', '⣕', '⣖', '⣗',
            '⣘', '⣙', '⣚', '⣛', '⣜', '⣝', '⣞', '⣟',
            '⣠', '⣡', '⣢', '⣣', '⣤', '⣥', '⣦', '⣧',
            '⣨', '⣩', '⣪', '⣫', '⣬', '⣭', '⣮', '⣯',
            '⣰', '⣱', '⣲', '⣳', '⣴', '⣵', '⣶', '⣷',
            '⣸', '⣹', '⣺', '⣻', '⣼', '⣽', '⣾', '⣿'
        ])

    def get_video_info(self, video_path: str) -> Tuple[float, int, int]:
        video = cv2.VideoCapture(video_path)
        if not video.isOpened():
            raise Exception("无法打开视频文件")
        
        fps = video.get(cv2.CAP_PROP_FPS)
        width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        video.release()
        
        return fps, width, height

    async def convert_video_to_braille(self, video_path: str) -> AsyncGenerator[str, None]:
        video = cv2.VideoCapture(video_path)

        if not video.isOpened():
            raise Exception("无法打开视频文件")

        try:
            while True:
                ret, frame = video.read()
                if not ret:
                    break

                braille_frame = self._image_to_braille(frame)
                yield braille_frame

                # 允许其他协程运行
                await asyncio.sleep(0)
        finally:
            video.release()

    def _image_to_braille(self, frame: np.ndarray) -> str:
        try:
            # 转换为灰度图
            if len(frame.shape) == 3:
                grey_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                grey_frame = frame

            # 调整大小
            small_grey_frame = cv2.resize(grey_frame, (self.width, self.height), interpolation=cv2.INTER_AREA)

            # 二值化处理
            _, binary_frame = cv2.threshold(small_grey_frame, 127, 255, cv2.THRESH_BINARY)

            return self._binary_image_to_braille(binary_frame)
        except Exception as e:
            return f"图像转换失败: {str(e)}"

    def _binary_image_to_braille(self, image: np.ndarray) -> str:
        try:
            height, width = image.shape
            
            # 确保尺寸是合适的倍数
            if width % 2 != 0 or height % 4 != 0:
                new_width = (width // 2) * 2
                new_height = (height // 4) * 4
                image = image[:new_height, :new_width]
                height, width = image.shape

            # 预分配输出字符串
            output_lines = []
            
            # 向量化处理提高效率
            for y in range(0, height, 4):
                line_chars = []
                for x in range(0, width, 2):
                    # 构造8位二进制数表示一个盲文字符
                    # 位置: 1 4
                    #      2 5
                    #      3 6
                    #      7 8
                    bits = 0
                    
                    # 检查8个点位
                    if y < height and x < width and image[y, x] == 0:          # 位置1
                        bits |= 1
                    if y + 1 < height and x < width and image[y + 1, x] == 0:    # 位置2
                        bits |= 2
                    if y + 2 < height and x < width and image[y + 2, x] == 0:    # 位置3
                        bits |= 4
                    if y + 3 < height and x < width and image[y + 3, x] == 0:    # 位置7
                        bits |= 64
                    if y < height and x + 1 < width and image[y, x + 1] == 0:    # 位置4
                        bits |= 8
                    if y + 1 < height and x + 1 < width and image[y + 1, x + 1] == 0:  # 位置5
                        bits |= 16
                    if y + 2 < height and x + 1 < width and image[y + 2, x + 1] == 0:  # 位置6
                        bits |= 32
                    if y + 3 < height and x + 1 < width and image[y + 3, x + 1] == 0:  # 位置8
                        bits |= 128

                    # 添加字符
                    line_chars.append(self.braille_chars[bits])

                output_lines.append(''.join(line_chars))

            return '\n'.join(output_lines)
        except Exception as e:
            return f"盲文转换失败: {str(e)}"