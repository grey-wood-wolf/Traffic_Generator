import socket
import threading
import queue
import subprocess
import argparse

class UDPHandler:
    def __init__(self, reserve_rate=0.5, new_rate=0.2, new_content='-uestc-'):
        # 调试模式控制
        self.DEBUG = False
        # 保留率
        self.reserved_rate = reserve_rate
        # 新增率
        self.new_rate = new_rate
        # 新增内容
        self.new_content = new_content
    
    def handle(self, data):
        original_length = len(data)
        cut_length = int(original_length* self.reserved_rate)  
        custom_length = int(original_length * self.new_rate)  
        
        truncated_data = data[:cut_length]  # 截取原始数据
        # 生成自定义内容（可根据需求修改此处）
        custom_data = self.new_content.encode() * (custom_length // len(self.new_content))  # 重复自定义内容以填充长度
        if len(custom_data) < custom_length:
            custom_data += self.new_content.encode()[:custom_length - len(custom_data)]
        # 合并自定义内容和截取数据
        new_data = truncated_data + custom_data
        if self.DEBUG:
            print(f"处理数据: 原始长度={original_length}, 截取长度={cut_length}, 新增长度={custom_length}")
        return new_data
        
class UDPForwarder:
    def __init__(self, reserve_rate=0.5, new_rate=0.2, new_content='-uestc-'):
        self.udp_handler = UDPHandler(reserve_rate, new_rate, new_content)

class UDPForwarder_426(UDPForwarder):
    def __init__(self, forward_config, handler_config):

        listen_port, ipv6_address, ipv6_port = forward_config['listen_port'], forward_config['target_address'], forward_config['target_port']
        reserve_rate, new_rate, new_content = handler_config['reserve_rate'], handler_config['new_rate'], handler_config['new_content']

        # 调用父类构造函数
        super().__init__(reserve_rate, new_rate, new_content)

        # 调试模式控制
        self.DEBUG = False  # 设为False关闭调试信息
        
        # IPv4监听配置
        self.ipv4_port = listen_port  # 监听的IPv4端口

        # 目的地址设置
        self.ipv6_address = ipv6_address  # 目标IPv6地址
        self.ipv6_port = ipv6_port  # 目标IPv6端口

        # 客户端会话 {客户端ID: 会话信息}
        self.sessions = {}

        # 创建主IPv4监听socket
        self.sock_ipv4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_ipv4.bind(('0.0.0.0', self.ipv4_port))

    def start(self):
        try:
            # 主循环 - 接受新连接并为每个客户端创建会话
            while True:
                data, addr = self.sock_ipv4.recvfrom(65535)
                client_ip, client_port = addr
                
                # 生成客户端唯一标识
                client_id = f"{client_ip}:{client_port}"
                
                if client_id not in self.sessions:
                    if self.DEBUG:
                        print(f"新客户端连接: {client_id}")
                    
                    # 创建新会话
                    self._create_session(client_ip, client_port, client_id)
                
                # 将数据放入对应会话的队列
                self.sessions[client_id]['queue'].put(data)
                
        except KeyboardInterrupt:
            if self.DEBUG:
                print("转发器关闭")
            self.sock_ipv4.close()
            
    def _create_session(self, client_ip, client_port, client_id):
        """为新客户端创建一个会话"""
        # 创建数据队列
        data_queue = queue.Queue()
        
        # 创建IPv6 socket
        sock_ipv6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        
        # 设置socket选项
        sock_ipv6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock_ipv6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # 绑定到IPv6地址和与客户端相同的端口
        try:
            sock_ipv6.bind(('::', client_port))  # 使用与IPv4客户端相同的端口
            if self.DEBUG:
                print(f"IPv6 socket绑定到端口: {client_port}")
        except Exception as e:
            if self.DEBUG:
                print(f"IPv6 socket绑定错误: {e}")
            return None
        
        # 创建会话记录
        session = {
            'client_ip': client_ip,
            'client_port': client_port,
            'ipv6_socket': sock_ipv6,
            'queue': data_queue,
            'active': True
        }
        
        # 存储会话
        self.sessions[client_id] = session
        
        # 创建并启动转发线程
        forward_thread = threading.Thread(
            target=self._ipv4_to_ipv6_handler,
            args=(session, client_id),
            daemon=True
        )
        
        backward_thread = threading.Thread(
            target=self._ipv6_to_ipv4_handler,
            args=(session, client_id),
            daemon=True
        )
        
        forward_thread.start()
        backward_thread.start()
        
        return session
    
    def _ipv4_to_ipv6_handler(self, session, client_id):
        """处理IPv4到IPv6方向的数据流"""
        sock_ipv6 = session['ipv6_socket']
        client_ip = session['client_ip']
        client_port = session['client_port']
        
        # 构造IPv6目标地址（全局地址，不需要接口标识符）
        ipv6_dest = (self.ipv6_address, self.ipv6_port)
        
        try:
            while session['active']:
                try:
                    # 从队列获取数据
                    data = session['queue'].get(timeout=1.0)

                    new_data = self.udp_handler.handle(data)  # 处理数据
                    
                    # 发送到IPv6目标
                    try:
                        sock_ipv6.sendto(new_data, ipv6_dest)
                        if self.DEBUG:
                            print(f"IPv4→IPv6: {client_ip}:{client_port} → [{self.ipv6_address}]:{self.ipv6_port}")
                    except Exception as e:
                        if self.DEBUG:
                            print(f"IPv6发送错误: {e}")
                    
                except queue.Empty:
                    # 队列为空，继续等待
                    continue
                    
        except Exception as e:
            if self.DEBUG:
                print(f"IPv4→IPv6处理错误 ({client_id}): {e}")
            session['active'] = False
    
    def _ipv6_to_ipv4_handler(self, session, client_id):
        """处理IPv6到IPv4方向的数据流"""
        sock_ipv6 = session['ipv6_socket']
        client_ip = session['client_ip']
        client_port = session['client_port']

        try:
            # 设置接收超时
            sock_ipv6.settimeout(1.0)
            
            while session['active']:
                try:
                    # 接收来自IPv6的数据
                    data, addr = sock_ipv6.recvfrom(65535)
                    
                    # 发送回IPv4客户端
                    self.sock_ipv4.sendto(data, (client_ip, client_port))
                    
                    if self.DEBUG:
                        src_addr = f"[{addr[0]}]:{addr[1]}" if len(addr) >= 2 else "未知"
                        print(f"IPv6→IPv4: {src_addr} → {client_ip}:{client_port}")
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.DEBUG:
                        print(f"处理IPv6数据包错误: {e}")
        
        except Exception as e:
            if self.DEBUG:
                print(f"IPv6→IPv4处理错误 ({client_id}): {e}")
            session['active'] = False

class UDPForwarder_624(UDPForwarder):
    def __init__(self, forward_config, handler_config):

        listen_port, ipv4_address, ipv4_port = forward_config['listen_port'], forward_config['target_address'], forward_config['target_port']
        reserve_rate, new_rate, new_content = handler_config['reserve_rate'], handler_config['new_rate'], handler_config['new_content']

        # 调用父类构造函数
        super().__init__(reserve_rate, new_rate, new_content)

        # 调试模式控制
        self.DEBUG = False  # 设为False关闭调试信息
        
        # IPv6监听配置
        self.ipv6_port = listen_port  # 监听的IPv6端口

        # 目的地址设置
        self.ipv4_address = ipv4_address  # 目标IPv4地址
        self.ipv4_port = ipv4_port  # 目标IPv4端口

        # 客户端会话 {客户端ID: 会话信息}
        self.sessions = {}

        # 创建主IPv6监听socket
        self.sock_ipv6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        self.sock_ipv6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        self.sock_ipv6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock_ipv6.bind(('::', self.ipv6_port))

    def start(self):
        try:
            # 主循环 - 接受新连接并为每个客户端创建会话
            while True:
                data, addr = self.sock_ipv6.recvfrom(65535)
                client_id = f"{addr[0]}%{addr[1]}"  # 使用%分隔IPv6地址和端口
                
                if client_id not in self.sessions:
                    if self.DEBUG:
                        print(f"新客户端连接: {client_id}")
                    
                    # 创建新会话
                    if self._create_session(addr, client_id) is None:
                        continue
                
                # 将数据放入对应会话的队列
                self.sessions[client_id]['queue'].put(data)
                
        except KeyboardInterrupt:
            if self.DEBUG:
                print("转发器关闭")
            self.sock_ipv6.close()
            
    def _create_session(self, client_addr, client_id):
        """为新客户端创建一个会话"""
        # 创建数据队列
        data_queue = queue.Queue()
        
        # 创建IPv4 socket
        sock_ipv4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        try:
            # 绑定到随机可用端口
            sock_ipv4.bind(('0.0.0.0', client_addr[1]))
            if self.DEBUG:
                bound_port = sock_ipv4.getsockname()[1]
                print(f"IPv4 socket绑定到端口: {bound_port}")
        except Exception as e:
            if self.DEBUG:
                print(f"IPv4 socket绑定错误: {e}")
            return None
        
        # 创建会话记录
        session = {
            'client_addr': client_addr,
            'ipv4_socket': sock_ipv4,
            'queue': data_queue,
            'active': True
        }
        
        # 存储会话
        self.sessions[client_id] = session
        
        # 创建并启动转发线程
        forward_thread = threading.Thread(
            target=self._ipv6_to_ipv4_handler,
            args=(session, client_id),
            daemon=True
        )
        
        backward_thread = threading.Thread(
            target=self._ipv4_to_ipv6_handler,
            args=(session, client_id),
            daemon=True
        )
        
        forward_thread.start()
        backward_thread.start()
        
        return session
    
    def _ipv6_to_ipv4_handler(self, session, client_id):
        """处理IPv6到IPv4方向的数据流"""
        sock_ipv4 = session['ipv4_socket']
        dest_address = (self.ipv4_address, self.ipv4_port)
        
        try:
            while session['active']:
                try:
                    # 从队列获取数据
                    data = session['queue'].get(timeout=1.0)

                    new_data = self.udp_handler.handle(data)  # 处理数据
                    
                    # 发送到IPv4目标
                    try:
                        sock_ipv4.sendto(new_data, dest_address)
                        if self.DEBUG:
                            client_addr = session['client_addr']
                            print(f"IPv6→IPv4: [{client_addr[0]}]:{client_addr[1]} → {dest_address[0]}:{dest_address[1]}")
                    except Exception as e:
                        if self.DEBUG:
                            print(f"IPv4发送错误: {e}")
                        session['active'] = False
                    
                except queue.Empty:
                    # 队列为空，继续等待
                    continue
                    
        except Exception as e:
            if self.DEBUG:
                print(f"IPv6→IPv4处理错误 ({client_id}): {e}")
            session['active'] = False
    
    def _ipv4_to_ipv6_handler(self, session, client_id):
        """处理IPv4到IPv6方向的数据流"""
        sock_ipv4 = session['ipv4_socket']
        client_addr = session['client_addr']

        try:
            # 设置接收超时
            sock_ipv4.settimeout(1.0)
            
            while session['active']:
                try:
                    # 接收来自IPv4的数据
                    data, addr = sock_ipv4.recvfrom(65535)
                    
                    # 发送回IPv6客户端
                    self.sock_ipv6.sendto(data, client_addr)
                    
                    if self.DEBUG:
                        print(f"IPv4→IPv6: {addr[0]}:{addr[1]} → [{client_addr[0]}]:{client_addr[1]}")
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.DEBUG:
                        print(f"处理IPv4数据包错误: {e}")
                    session['active'] = False
        
        except Exception as e:
            if self.DEBUG:
                print(f"IPv4→IPv6处理错误 ({client_id}): {e}")
            session['active'] = False

class SocatTCPForwarder:
    def __init__(self, ipv4_address, ipv4_port, ipv6_address, ipv6_port):
        self.ipv4_address = ipv4_address
        self.ipv4_port = ipv4_port
        self.ipv6_address = ipv6_address
        self.ipv6_port = ipv6_port

        self.ipv4_command = [
            'socat', 
            f'TCP4-LISTEN:{self.ipv4_port},fork',
            f'TCP6:[{self.ipv6_address}]:{self.ipv6_port}'
        ]

        self.ipv6_command = [
            'socat', 
            f'TCP6-LISTEN:{self.ipv6_port},fork,ipv6only=1', 
            f'TCP4:{self.ipv4_address}:{self.ipv4_port}'
        ]

    def start_socat(self, command):
        subprocess.Popen(command)

    def start(self):
        # 启动两个socat进程
        ipv4_thread = threading.Thread(target=self.start_socat, args=(self.ipv4_command,))
        ipv6_thread = threading.Thread(target=self.start_socat, args=(self.ipv6_command,))

        # 设置为守护线程，程序退出时会自动终止
        ipv4_thread.daemon = True
        ipv6_thread.daemon = True

        ipv4_thread.start()
        ipv6_thread.start()

        ipv4_thread.join()
        ipv6_thread.join()

def parse_arguments():
    parser = argparse.ArgumentParser(description="设置 Forwarder 相关参数")
    
    # 添加命令行参数
    parser.add_argument('--ipv4_addr', type=str, default='172.17.0.3', help='IPv4 地址')
    parser.add_argument('--ipv4_port', type=int, default=5201, help='IPv4 端口')
    parser.add_argument('--ipv6_addr', type=str, default='2001:db8::2', help='IPv6 地址')
    parser.add_argument('--ipv6_port', type=int, default=5201, help='IPv6 端口')
    
    # 额外的参数
    parser.add_argument('--reserve_rate', type=float, default=0.5, help='预留率')
    parser.add_argument('--new_rate', type=float, default=0.2, help='添加率')
    parser.add_argument('--new_content', type=str, default='-uestc-', help='新内容')

    # 版本参数
    parser.add_argument('-v', '--version', action='store_true', help='print version')
    
    # 解析命令行参数
    return parser.parse_args()

if __name__ == '__main__':

    args = parse_arguments()

    if args.version:
        print('udp_forwarder: 1.0.0')
    else:
        ipv4_address = args.ipv4_addr
        ipv4_port = args.ipv4_port
        ipv6_address = args.ipv6_addr
        ipv6_port = args.ipv6_port
        reserve_rate = args.reserve_rate
        new_rate = args.new_rate
        new_content = args.new_content

        print(10 * '-' + '开始转发' + 10 * '-')
        print(f"IPv4 地址: {ipv4_address}, IPv4 端口: {ipv4_port}")
        print(f"IPv6 地址: {ipv6_address}, IPv6 端口: {ipv6_port}")
        print(f"预留率: {reserve_rate}, 添加率: {new_rate}, 新内容: {new_content}")

        forward_config_624 = {
            'listen_port': ipv6_port,
            'target_address': ipv4_address,
            'target_port': ipv4_port
        }
        forward_config_426 = {
            'listen_port': ipv4_port,
            'target_address': ipv6_address,
            'target_port': ipv6_port
        }
        handler_config = {
            'reserve_rate': reserve_rate,
            'new_rate': new_rate,
            'new_content': new_content
        }

        socat_forwarder = SocatTCPForwarder(ipv4_address=ipv4_address, ipv4_port=ipv4_port, ipv6_address=ipv6_address, ipv6_port=ipv6_port)
        socat_forwarder.start()

        forwarder_624 = UDPForwarder_624(forward_config=forward_config_624, handler_config=handler_config)
        forwarder_426 = UDPForwarder_426(forward_config=forward_config_426, handler_config=handler_config)

        threading_624 = threading.Thread(target=forwarder_624.start, daemon=True)
        threading_426 = threading.Thread(target=forwarder_426.start, daemon=True)

        threading_624.start()
        threading_426.start()
        threading_624.join()
        threading_426.join()


# 运行示例
# python3 udp_forwarder.py --ipv4_addr 172.17.0.3 --ipv4_port 5201 --ipv6_addr 2001:db8::2 --ipv6_port 5201 --reserve_rate 0.5 --new_rate 0.2 --new_content '-uestc-'