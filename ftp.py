import socket
import sys
from threading import Thread
import os.path
from tqdm import tqdm
import shutil


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
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def get_files(path) -> list:
    file_list = os.listdir(path)
    ret = []
    for file in file_list:
        file_path = os.path.join(path, file)
        if os.path.isdir(file):
            ret.extend(get_files(file_path))
        else:
            ret.append(file_path)
    return ret


def send_file(file_path: str, socket_client: socket.socket):
    # 删除冗余引号
    if file_path.startswith('"') and file_path.endswith('"'):
        file_path = file_path[1:-1]
    if file_path.startswith("'") and file_path.endswith("'"):
        file_path = file_path[1:-1]
    if not os.path.exists(file_path):
        my_print(f"[Error] 文件 {file_path} 不存在！", "red", True)
        return
    if os.path.isfile(file_path):
        # 如果传进来的是个文件
        file_list = [file_path]
    else:
        # 如果传进来的是个文件夹
        file_list = get_files(file_path)
    for file_path in file_list:
        # 获取文件名
        file_name = os.path.basename(file_path)
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        # 发送文件名
        socket_client.sendall(file_name.encode())
        socket_client.recv(BUFFER_SIZE)
        # 发送文件大小
        socket_client.sendall(str(file_size).encode())
        socket_client.recv(BUFFER_SIZE)
        # 发送文件内容
        my_print(f"[Info] 文件 {file_path} 开始发送，大小:{file_size}B。")
        pbar = tqdm(total=file_size, desc="发送：" + file_name, unit="B", unit_scale=True)
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(BUFFER_SIZE)
                if not data:
                    break
                socket_client.sendall(data)
                pbar.update(len(data))
        socket_client.recv(BUFFER_SIZE)
        pbar.close()
        my_print(f"[Success] 文件 {file_path} 发送完成。", "green", True)


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
    # 然后问问是不是要把文件夹里的东西都发出去
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
            my_print("[Info] 程序退出。", "blue", True)
            sys.exit(0)
        send_file(file_path, socket_client)


def as_server(host: str, port: int):
    socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 创建IPv4，TCP套接字
    socket_server.bind((host, port))
    if not os.path.exists(FOLDER_RECV):
        os.mkdir(FOLDER_RECV)
    file_size = 0
    file_size_recv = 0
    file_name = ''
    file_path = ''
    socket_server.listen(128)
    socket_client, addr = socket_server.accept()
    state = 0
    while True:
        raw_data = socket_client.recv(BUFFER_SIZE)
        if state == 0:
            file_name = raw_data.decode()
            if file_name == 'EXIT':
                socket_client.close()
                my_print("[Info] 程序退出。", "blue", True)
                sys.exit(0)
            file_path = os.path.join(FOLDER_RECV, file_name)
            my_print(f"[Info] 接收的文件名：{file_name}")
            socket_client.sendall(b'OK')
            state = 1
        elif state == 1:
            file_size = int(raw_data.decode())
            my_print(f"[Info] 接收的文件大小：{file_size}B")
            socket_client.sendall(b'OK')
            if file_size:
                pbar = tqdm(total=file_size, desc="接收：" + file_name, unit='B', unit_scale=True)
                state = 2
            else:
                # 如果只是一个空文件
                with open(file_path, 'ab') as f:
                    f.close()
                socket_client.sendall(b'OK')
                state = 0
        elif state == 2:
            with open(file_path, 'ab') as f:
                f.write(raw_data)
            data_size = len(raw_data)
            file_size_recv += data_size
            pbar.update(data_size)
            if file_size_recv == file_size:
                socket_client.send(b'OK')
                pbar.close()
                my_print(f"[Success] 文件 {file_name} 接收完成。", "green", True)
                my_print("[Input] 请输入文件路径，0退出程序：", "blue", True)
                file_name = ''
                file_path = ''
                file_size = 0
                file_size_recv = 0
                state = 0


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
