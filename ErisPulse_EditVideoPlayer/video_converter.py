import cv2
import asyncio


class VideoConverter:
    def __init__(self, width: int = 60, height: int = 30):
        # 更适合移动端的默认比例
        self.width = width
        self.height = height
        self.braille_chars = (
            '⠀⠁⠂⠃⠄⠅⠆⠇⠈⠉⠊⠋⠌⠍⠎⠏⠐⠑⠒⠓⠔⠕⠖⠗⠘⠙⠚⠛⠜⠝⠞⠟'
            '⠠⠡⠢⠣⠤⠥⠦⠧⠨⠩⠪⠫⠬⠭⠮⠯⠰⠱⠲⠳⠴⠵⠶⠷⠸⠹⠺⠻⠼⠽⠾⠿'
            '⡀⡁⡂⡃⡄⡅⡆⡇⡈⡉⡊⡋⡌⡍⡎⡏⡐⡑⡒⡓⡔⡕⡖⡗⡘⡙⡚⡛⡜⡝⡞⡟'
            '⡠⡡⡢⡣⡤⡥⡦⡧⡨⡩⡪⡫⡬⡭⡮⡯⡰⡱⡲⡳⡴⡵⡶⡷⡸⡹⡺⡻⡼⡽⡾⡿'
            '⢀⢁⢂⢃⢄⢅⢆⢇⢈⢉⢊⢋⢌⢍⢎⢏⢐⢑⢒⢓⢔⢕⢖⢗⢘⢙⢚⢛⢜⢝⢞⢟'
            '⢠⢡⢢⢣⢤⢥⢦⢧⢨⢩⢪⢫⢬⢭⢮⢯⢰⢱⢲⢳⢴⢵⢶⢷⢸⢹⢺⢻⢼⢽⢾⢿'
            '⣀⣁⣂⣃⣄⣅⣆⣇⣈⣉⣊⣋⣌⣍⣎⣏⣐⣑⣒⣓⣔⣕⣖⣗⣘⣙⣚⣛⣜⣝⣞⣟'
            '⣠⣡⣢⣣⣤⣥⣦⣧⣨⣩⣪⣫⣬⣭⣮⣯⣰⣱⣲⣳⣴⣵⣶⣷⣸⣹⣺⣻⣼⣽⣾⣿'
        )

    async def convert_video_to_braille(self, video_path: str):
        video = cv2.VideoCapture(video_path)

        if not video.isOpened():
            raise Exception("无法打开视频文件")

        frame_count = 0
        try:
            while True:
                ret, frame = video.read()
                if not ret:
                    break

                # 每隔一定帧数处理一次，控制播放速度
                if frame_count % 2 == 0:
                    braille_frame = self._image_to_braille(frame)
                    yield braille_frame

                frame_count += 1

                # 允许其他协程运行
                await asyncio.sleep(0)
        finally:
            video.release()

    def _image_to_braille(self, frame):
        try:
            grey_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small_grey_frame = cv2.resize(grey_frame, (self.width, self.height))

            _, binary_frame = cv2.threshold(small_grey_frame, 127, 255, cv2.THRESH_BINARY)

            return self._binary_image_to_braille(binary_frame)
        except Exception as e:
            return f"图像转换失败: {str(e)}"

    def _binary_image_to_braille(self, image):
        output = ''

        height, width = image.shape
        if width % 2 != 0 or height % 3 != 0:
            new_width = (width // 2) * 2
            new_height = (height // 3) * 3
            image = image[:new_height, :new_width]
            height, width = image.shape

        for y in range(0, height, 3):
            for x in range(0, width, 2):
                # 构造6位二进制数表示一个盲文字符
                num = 0
                # 按照盲文点阵的顺序读取像素值 (从左到右，从上到下)
                # 位置: 1 4
                #      2 5
                #      3 6
                positions = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
                for i, (dx, dy) in enumerate(positions):
                    pixel_y = y + dy
                    pixel_x = x + dx
                    if pixel_y < height and pixel_x < width:
                        # 黑色点(0)表示有点，白色点(255)表示无点
                        if image[pixel_y][pixel_x] == 0:
                            num |= (1 << i)

                # 添加字符
                if num < len(self.braille_chars):
                    output += self.braille_chars[num]
                else:
                    output += '⠀'

            output += '\n'

        return output.rstrip('\n')