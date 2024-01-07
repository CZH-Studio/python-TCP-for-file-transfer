# 非常简单的python文件传输脚本
## 环境配置

```cmd
pip install tqdm
```

`tqdm`也只是起到一个显示进度条的作用，如果不想下载的话把代码中有关`tqdm`的语句删除即可。

## 使用

1. 主程序：`ftp.py`
2. 在Windows下可以运行`ftp.bat`，文件传输完成后自动打开输出文件夹（需要手动修改该文件中的文件路径）
3. 第一次运行后，会在文件夹下出现`ftp-recv`和`ftp-send`两个文件夹，分别存放待发送的文件和接收的文件，程序刚开始执行时会扫描`ftp-recv`文件夹下是否有文件，如果有的话会提示是否先把这个文件夹内的所有文件发送出去，因此这个文件夹充当中转站的作用
4. 在`ftp-recv`还会生成一个`config.txt`，为上次连接的IP地址；端口号指定`12345`，不改了。
5. 路径指定文件或文件夹都行，支持命令行传参，输入路径的时候带不带双引号都行
6. 使用TCP套接字传输，单线程
