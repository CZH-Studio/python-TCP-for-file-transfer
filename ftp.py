import socket
import sys
from threading import Thread
import os.path
from tqdm import tqdm
import shutil
import pickle


color_dict = {"red": 31, "green": 32, "yellow": 33, "blue": 34, "magenta": 35, "cyan": 36, "white": 37}
BUFFER_SIZE = 8192
FOLDER_RECV = 'ftp-recv'
FOLDER_SEND = 'ftp-send'


def colorful(s, color=None, highlight=False):
    try:
        assert color in [None, "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
    except AssertionError:
        my_print("[Warning] 颜色必须是以下颜色之一: None, 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white'！已默认为白色。", "yellow")
        return s
    highlight = 1 if highlight else 0
    if color:
        return f"\033[{highlight};{color_dict[color]}m{s}\033[m"
    else:
        return s


def my_input(prompt: str, t=str, color=None, highlight=False):
    while True:
        ret = input(colorful(prompt, color, highlight))
        if t is str:
            return ret
        try:
            ret = t(ret)
            return ret
        except NameError:
            my_print("[Warning] 输入函数传参时指定的类型不错误！已默认为str。", "yellow", True)
            return ret
        except TypeError:
            my_print("[Error] 输入错误，请重新输入！", "red", True)
            continue


def my_print(s, color=None, highlight=False):
    print(colorful(s, color, highlight))


def get_host_ip():
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def get_files(path, is_root=True) -> list[dict]:
    # 获取这个路径下的所有文件信息
    file_list = os.listdir(path)
    ret: list[dict] = []
    for file in file_list:
        file_path = os.path.join(path, file)
        if os.path.isdir(file_path):
            ret.extend(get_files(file_path, False))
        else:
            meta_data = {"path": file_path, "atime": os.path.getatime(file_path), "mtime": os.path.getmtime(file_path), "size": os.path.getsize(file_path)}
            ret.append(meta_data)
    if is_root:
        # 在根目录下将所有的文件目录替换为相对于根目录的路径，而不是绝对路径
        root_length = len(path)
        for i in range(len(ret)):
            path_string = ret[i]["path"]
            path_string = path_string[root_length + 1:]
            path_string = path_string.replace('\\', '/')
            ret[i]["path"] = path_string
    return ret


def get_dirs(path, is_root=True) -> list[dict]:
    # 获取这个路径下的所有文件夹信息
    file_list = os.listdir(path)
    ret: list[dict] = []
    for file in file_list:
        file_path = os.path.join(path, file)
        if os.path.isdir(file_path):
            # 如果是一个文件夹，则获取文件夹的路径和元数据
            meta_data = {"path": file_path, "atime": os.path.getatime(file_path), "mtime": os.path.getmtime(file_path)}
            ret.append(meta_data)
            ret.extend(get_dirs(file_path, False))
    if is_root:
        # 在根目录下将所有的文件目录替换为相对于根目录的路径，而不是绝对路径
        root_length = len(path)
        for i in range(len(ret)):
            dir_string: str = ret[i]["path"]
            dir_string = dir_string[root_length + 1:]
            dir_string = dir_string.replace('\\', '/')
            ret[i]["path"] = dir_string
    return ret


def send_file(file_path: str, socket_client: socket.socket):
    # 删除冗余引号
    if file_path.startswith('"') and file_path.endswith('"'):
        file_path = file_path[1:-1]
    if file_path.startswith("'") and file_path.endswith("'"):
        file_path = file_path[1:-1]
    # 正则化路径，统一\\符号为/符号
    file_path = file_path.replace('\\', '/')
    # 判断传进来的路径是否存在
    if not os.path.exists(file_path):
        my_print(f"[Error] 文件 {file_path} 不存在！", "red", True)
        return
    if os.path.isfile(file_path):
        # 如果传进来的是个文件，则只获取这个文件的文件名，发送后保存在接受文件夹的根目录下
        file_list = {"path": os.path.basename(file_path), "atime": os.path.getatime(file_path), "mtime": os.path.getmtime(file_path), "size": os.path.getsize(file_path)}
        root_path = os.path.dirname(file_path)
        # 此时不需要获取文件夹结构
        dir_list = []
    else:
        # 如果传进来的是个文件夹，则需要获取整个文件夹的文件结构，接收方根据文件夹结构保存文件
        file_list = get_files(file_path)
        # 同时还需获取目录结构，接收方需要先创建对应的目录
        dir_list = get_dirs(file_path)
        # 为了之后能够正确读取文件，需要把根目录保存
        root_path = file_path
    # 告诉服务器端跳转到文件夹创建状态
    socket_client.sendall(b'DIR')
    # 等待服务器端状态转换完成
    socket_client.recv(BUFFER_SIZE)

    # 向服务器端发送目录结构
    socket_client.sendall(pickle.dumps(dir_list))
    socket_client.recv(BUFFER_SIZE)

    # 开始传送文件
    for meta_data in file_list:
        # file_list中保存的是每一个文件的元数据
        file_path_relative = meta_data["path"]
        file_size: int = meta_data["size"]
        file_path_absolute = os.path.join(root_path, file_path_relative)
        # 发送文件元数据
        socket_client.sendall(pickle.dumps(meta_data))
        socket_client.recv(BUFFER_SIZE)
        # 发送文件内容
        my_print(f"[Info] 发送:{file_path_absolute} 大小:{file_size}B。")
        if file_size:
            pbar = tqdm(total=file_size, desc="进度", unit="B", unit_scale=True)
            with open(file_path_absolute, 'rb') as f:
                while True:
                    data = f.read(BUFFER_SIZE)
                    if not data:
                        break
                    socket_client.sendall(data)
                    pbar.update(len(data))
            socket_client.recv(BUFFER_SIZE)
            pbar.clear()
            pbar.close()
        my_print(f"[Success] 完成发送:{file_path_absolute}", "green", True)

    # 这一次文件发送完成后告诉服务器端
    meta_data_exit = {"path": "EXIT"}
    socket_client.sendall(pickle.dumps(meta_data_exit))
    socket_client.recv(BUFFER_SIZE)


def as_client(host: str, port: int):
    socket_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_client.connect((host, port))
    # 首先发送从命令行传过来的参数
    if len(sys.argv) > 1:
        my_print("[Info] 开始发送从命令行传递的参数对应的文件。")
        for arg in sys.argv[1:]:
            send_file(arg, socket_client)

    # 然后看看ftp-send文件夹里有没有东西
    if not os.path.exists(FOLDER_SEND):
        os.mkdir(FOLDER_SEND)
    # 问问是不是要把文件夹里的东西都发出去
    if len(os.listdir(FOLDER_SEND)):
        send = my_input(f"[Input] 是否发送 {FOLDER_SEND} 文件夹里的文件？([1]/0):", str, "blue", True)
        if send != '0':
            send_file(FOLDER_SEND, socket_client)
            delete = my_input(f"[Input] 是否删除 {FOLDER_SEND} 文件夹里的文件？([1]/0):", str, "blue", True)
            if delete != '0':
                shutil.rmtree(FOLDER_SEND)
                os.mkdir(FOLDER_SEND)

    # 最后手动发送
    while True:
        file_path = my_input("[Input] 请输入文件路径，0/空退出程序：", str, "blue", True)
        # 判断是否退出程序
        if file_path == '0' or file_path == '':
            socket_client.send(b'EXIT')
            socket_client.close()
            my_print("[Info] 本端程序退出，请在另一端回车退出程序。", "blue", True)
            sys.exit(0)
        send_file(file_path, socket_client)


def as_server(host: str, port: int):
    socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 创建IPv4，TCP套接字
    socket_server.bind((host, port))
    if not os.path.exists(FOLDER_RECV):
        os.mkdir(FOLDER_RECV)
    file_size = 0
    file_size_recv = 0
    file_path_relative = ''
    file_path_absolute = ''
    atime = 0
    mtime = 0
    socket_server.listen(128)
    socket_client, addr = socket_server.accept()
    # 状态0：就绪
    state = 0
    while True:
        if state == 0:
            # 就绪状态：接收EXIT（退出程序）或DIR（开始创建文件夹结构）
            raw_data = socket_client.recv(BUFFER_SIZE)
            action = raw_data.decode()
            if action == 'EXIT':
                # 退出程序
                socket_client.close()
                my_print("[Info] 另一端的程序退出，请回车关闭本端程序。", "blue", True)
                sys.exit(0)
            elif action == 'DIR':
                # 进入文件夹创建状态
                state = 1
            else:
                # 接收到了错误的字符串，回归状态0
                state = 0
            socket_client.sendall(b'OK')
        elif state == 1:
            # 接收文件夹元数据
            raw_data = socket_client.recv(BUFFER_SIZE)
            dir_list: list[dict] = pickle.loads(raw_data)
            # 创建对应的文件夹，并指定文件夹的元数据
            for meta_data in dir_list:
                dir_path_relative = meta_data['path']
                dir_path_absolute = os.path.join(FOLDER_RECV, dir_path_relative)
                atime = meta_data['atime']
                mtime = meta_data['mtime']
                os.makedirs(dir_path_absolute, exist_ok=True)
                os.utime(dir_path_absolute, (atime, mtime))
            # 创建完成后进入文件传输状态
            socket_client.sendall(b'OK')
            state = 2
        elif state == 2:
            # 接收文件元数据（是一个字典），如果文件元数据是退出，则代表当前一次文件传输完成，回到状态0
            raw_data = socket_client.recv(BUFFER_SIZE)
            meta_data: dict = pickle.loads(raw_data)
            file_path_relative = meta_data['path']
            if file_path_relative == 'EXIT':
                socket_client.sendall(b'OK')
                state = 0
                continue
            file_path_absolute = os.path.join(FOLDER_RECV, file_path_relative)
            file_size = meta_data['size']
            atime = meta_data['atime']
            mtime = meta_data['mtime']
            my_print(f"[Info] 接收:{file_path_absolute} 大小:{file_size}B")
            socket_client.sendall(b'OK')
            if file_size:
                # 如果不是空文件，则跳转到文件数据接收状态
                state = 3
            else:
                # 如果只是一个空文件
                with open(file_path_absolute, 'ab') as f:
                    f.close()
                socket_client.sendall(b'OK')
                state = 2
                # 修改文件元数据
                os.utime(file_path_absolute, (atime, mtime))
                my_print(f"[Success] 完成接收:{file_path_absolute}", "green", True)
        elif state == 3:
            # 接收文件内容状态
            # 创建进度条
            pbar = tqdm(total=file_size, desc="进度", unit='B', unit_scale=True)
            # 持续接收文件
            with open(file_path_absolute, 'ab') as f:
                while file_size_recv < file_size:
                    raw_data = socket_client.recv(BUFFER_SIZE)
                    f.write(raw_data)
                    data_size = len(raw_data)
                    file_size_recv += data_size
                    pbar.update(data_size)
            # 文件接收完毕，关闭进度条，发送完成信息
            socket_client.send(b'OK')
            pbar.clear()
            pbar.close()
            # 修改文件元数据
            os.utime(file_path_absolute, (atime, mtime))
            # 恢复初始状态
            my_print(f"[Success] 完成接收:{file_path_absolute}", "green", True)
            my_print("[Input] 请输入文件路径，0/空退出程序：", "blue", True)
            file_path_absolute = ''
            file_size = 0
            file_size_recv = 0
            atime = 0
            mtime = 0
            state = 2


def main():
    # 设定本身作为服务器的主机和端口号
    HOST_SERVER = get_host_ip()
    my_print("[Info] 本机IP地址：" + HOST_SERVER, "blue", True)
    PORT_SERVER = 12345
    # 设定文件传输目标主机和端口号
    if os.path.exists(f'./{FOLDER_RECV}/config.txt'):
        with open(f'./{FOLDER_RECV}/config.txt', 'r') as config:
            HOST_DESTINATION = config.read()
        use_last = my_input(f'[Input] 是否使用上次连接的配置：{HOST_DESTINATION} ([1]/0)？：', str, "blue", True)
        if use_last == '0':
            HOST_DESTINATION = my_input('[Input] 输入目标主机：', str, "blue", True)
            with open(f'./{FOLDER_RECV}/config.txt', 'w') as config:
                config.write(HOST_DESTINATION)
    else:
        HOST_DESTINATION = my_input('[Input] 输入目标主机：', str, "blue", True)
        with open(f'./{FOLDER_RECV}/config.txt', 'w') as config:
            config.write(HOST_DESTINATION)
    PORT_DESTINATION = 12345
    # 创建线程并启动
    thread_client = Thread(target=as_client, args=(HOST_DESTINATION, PORT_DESTINATION))
    thread_server = Thread(target=as_server, args=(HOST_SERVER, PORT_SERVER))
    thread_client.start()
    thread_server.start()
    thread_client.join()
    thread_server.join()


if __name__ == '__main__':
    main()
