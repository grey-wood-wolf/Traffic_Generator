import socket
import time
import threading
import struct

from FlowGenerator import FlowGenerator

class UDPPacket:
    # 添加包类型常量
    TYPE_INIT = 0xFFFFFFF0  # 建立连接请求
    TYPE_INIT_ACK = 0xFFFFFFF1  # 建立连接确认  
    TYPE_DATA = 0x0  # 普通数据包
    TYPE_FIN = 0xFFFFFFFF  # 结束包
    TYPE_FIN_ACK = 0xFFFFFFFE  # 结束确认包
    TYPE_FORCE_QUIT = 0xFFFFFFF2  # 强制退出类型
    TYPE_FORCE_QUIT_ACK = 0xFFFFFFF3  # 强制退出确认类型

    def __init__(self, seq_no, timestamp, total_packets=0, data=b''):
        self.seq_no = seq_no
        self.timestamp = timestamp 
        self.total_packets = total_packets
        self.data = data
        
    def to_bytes(self):
        header = struct.pack('!IQI', self.seq_no, self.timestamp, self.total_packets)
        return header + self.data
        
    @staticmethod 
    def from_bytes(data):
        header = data[:16]  # 4+8+4=16字节的包头
        seq_no, timestamp, total_packets = struct.unpack('!IQI', header)
        return UDPPacket(seq_no, timestamp, total_packets, data[16:])

class UDPFlowGenerator(FlowGenerator):
    def __init__(self, bind_address, host, port, mode, duration=None, total_size=None, packet_size=None, bandwidth=None,
                 interval=1, distributed_packets_per_second=None, distributed_packet_size=None,
                 distributed_bandwidth=None, bandwidth_reset_interval=None, json=False, one_test=False, ipv6=False, printpkg = False):
        if bandwidth is None:
            bandwidth = "1M"
        if packet_size is None:
            if bandwidth is not None:
                packet_size = min(1450, int(self.to_bps(bandwidth) * 0.005))
            else:
                packet_size = 1450
            packet_size = max(80, packet_size)  # UDP最小包大小为64字节
        if ipv6:
            pkt_head_size = 62 + 16 #16为流发生器所需伪包头
        else:
            pkt_head_size = 42 + 16
        super().__init__(bind_address, host, port, mode, duration, total_size, packet_size, bandwidth, interval,
                         distributed_packets_per_second, distributed_packet_size, distributed_bandwidth,  
                         bandwidth_reset_interval, json, one_test, ipv6, printpkg, pkt_head_size)
        self.type = 'udp'
        
    def create_test_data(self, seq_no):
        payload_size = self.packet_size - 16  # 减去包头大小
        test_data = b'x' * payload_size
        packet = UDPPacket(seq_no, int(time.time() * 1000000), 0, test_data)
        return packet.to_bytes()

    def run_server(self):
        try:
            if not self.bind_address:
                self.bind_address = '0.0.0.0' if not self.ipv6 else '::'
            socket_family = socket.AF_INET6 if self.ipv6 else socket.AF_INET
            server_socket = socket.socket(socket_family, socket.SOCK_DGRAM)
            server_socket.bind((self.bind_address, self.port))
            if not self.json:
                print(f"UDP Server listening on {self.bind_address}:{self.port}")

            while True:
                # 等待客户端发起连接
                if not self.json:
                    print("Waiting for client connection...")
                while True:
                    data, addr = server_socket.recvfrom(65535)
                    packet = UDPPacket.from_bytes(data)
                    if packet.seq_no == UDPPacket.TYPE_INIT:
                        # 发送确认包
                        ack_packet = UDPPacket(UDPPacket.TYPE_INIT_ACK, int(time.time() * 1000000))
                        server_socket.sendto(ack_packet.to_bytes(), addr)
                        break
                if not self.json:
                    print("Client connected, starting test...")
                self.received_packets_seq_no = set()
                self.total_sent = 0
                self.total_packets = 0
                self.max_seq_no = 0         # 最大的包序列号
                self.total_jitters = 0      # 总抖动
                self.total_delay = 0        # 总延迟
                
                self.is_running = True
                self.test_start_time = self.start_time = time.time()
                
                self.stats_thread = threading.Thread(target=self.print_statistics)
                self.stats_thread.daemon = True
                self.stats_thread.start()
                
                self.total_received_packets = 0
                self.total_sent_packets = 0
                self.forced_quit = False
                last_transit = 0
                
                try:
                    while self.is_running:
                        try:
                            data, addr = server_socket.recvfrom(65535)
                            packet = UDPPacket.from_bytes(data)

                            if packet.seq_no == UDPPacket.TYPE_FORCE_QUIT:
                                self.total_sent_packets = packet.total_packets
                                # 发送确认
                                ack_packet = UDPPacket(UDPPacket.TYPE_FORCE_QUIT_ACK, int(time.time() * 1000000), self.total_packets)
                                server_socket.sendto(ack_packet.to_bytes(), addr)
                                self.is_running = False
                                break
                            
                            if packet.seq_no == UDPPacket.TYPE_FIN:
                                self.total_sent_packets = packet.total_packets
                                ack_packet = UDPPacket(UDPPacket.TYPE_FIN_ACK, int(time.time() * 1000000), self.total_packets)
                                server_socket.sendto(ack_packet.to_bytes(), addr)
                                break
                                
                            self.max_seq_no = max(self.max_seq_no, packet.seq_no)
                            self.packet_size = len(data) # 跟新报文长度
                            self.frame_size = self.packet_size + self.pkt_head_size
                            self.total_sent += len(data) + self.pkt_head_size
                            self.total_packets += 1
                            transit = (time.time() - packet.timestamp / 1000000) * 1000 # 单位ms
                            self.total_jitters += abs(transit - last_transit)
                            last_transit = transit
                            self.total_delay += transit # 单位ms
                            if self.pkg_data == "None" and self.printpkg:
                                self.pkg_data = data.hex()

                        except Exception as e:
                            print(f"Error receiving data: {e}")
                            break

                except KeyboardInterrupt:
                    self.forced_quit = True
                    for _ in range(10):
                        if 'addr' in locals():
                            # 发送强制退出信号给客户端
                            quit_packet = UDPPacket(UDPPacket.TYPE_FORCE_QUIT, int(time.time() * 1000000), total_packets=self.total_packets)
                            server_socket.sendto(quit_packet.to_bytes(), addr)
                            # 等待确认
                            try:
                                server_socket.settimeout(0.1)
                                data, _ = server_socket.recvfrom(65535)
                                packet = UDPPacket.from_bytes(data)
                                if packet.seq_no == UDPPacket.TYPE_FORCE_QUIT_ACK:
                                    self.total_sent_packets = packet.total_packets
                                    break
                            except socket.timeout:
                                continue
                
                self.is_running = False
                self.test_end_time = time.time()
                if self.stats_thread:
                    self.stats_thread.join()
                
                if self.total_sent > 0:
                    self.print_summary()
                
                if self.one_test:
                    break

                if self.forced_quit:
                    break

        except Exception as e:
            print(f"Server error: {e}")
        finally:
            server_socket.close()

    def run_client(self):
        try:
            socket_family = socket.AF_INET6 if self.ipv6 else socket.AF_INET
            self.socket = socket.socket(socket_family, socket.SOCK_DGRAM)
            if not self.json:
                print(f"UDP Client connecting to {self.host}:{self.port}")
            
            # 发送建立连接请求
            for _ in range(10):  # 重试10次
                try:
                    init_packet = UDPPacket(UDPPacket.TYPE_INIT, int(time.time() * 1000000))
                    self.socket.sendto(init_packet.to_bytes(), (self.host, self.port))
                    
                    self.socket.settimeout(0.1)
                    data, _ = self.socket.recvfrom(65535)
                    packet = UDPPacket.from_bytes(data)
                    if packet.seq_no == UDPPacket.TYPE_INIT_ACK:
                        if not self.json:
                            print("Connection established")
                        break
                except socket.timeout:
                    continue
            else:
                raise Exception("Failed to establish connection")
            
            self.socket.settimeout(None)  # 恢复为阻塞模式
            
            self.is_running = True
            self.test_start_time = self.start_time = time.time()
            last_reset_time = self.start_time
            
            self.stats_thread = threading.Thread(target=self.print_statistics)
            self.stats_thread.daemon = True
            self.stats_thread.start()

            self.reset_bandwidth()
            seq_no = 1
            self.forced_quit = False

            if self.pps:
                next_send_time = time.time()
            try:
                while True:
                    if self.duration and time.time() - self.start_time >= self.duration:
                        break
                    if self.total_size and self.total_sent >= self.total_size:
                        break

                    if time.time() - last_reset_time >= self.bandwidth_reset_interval:
                        self.reset_bandwidth()
                        last_reset_time = time.time()
                        
                    # 添加非阻塞接收检查
                    self.socket.setblocking(False)
                    try:
                        data, _ = self.socket.recvfrom(65535)
                        packet = UDPPacket.from_bytes(data)
                        if packet.seq_no == UDPPacket.TYPE_FORCE_QUIT:
                            self.total_received_packets = packet.total_packets
                            # 发送确认
                            ack_packet = UDPPacket(UDPPacket.TYPE_FORCE_QUIT_ACK, int(time.time() * 1000000), self.total_packets)
                            self.socket.sendto(ack_packet.to_bytes(), (self.host, self.port))
                            self.forced_quit = True
                            break
                    except (socket.error, BlockingIOError):
                        pass
                    self.socket.setblocking(True)
                        
                    if self.pps:
                        current_time = time.time()
                        while True:
                            if current_time > next_send_time:
                                test_data = self.create_test_data(seq_no)
                                self.socket.sendto(test_data, (self.host, self.port))
                                self.total_sent += len(test_data) + self.pkt_head_size
                                self.total_packets += 1
                                seq_no += 1
                                next_send_time += self.return_packet_interval()
                            else:
                                break
                    else:
                        test_data = self.create_test_data(seq_no)
                        self.socket.sendto(test_data, (self.host, self.port))
                        self.total_sent += len(test_data) + self.pkt_head_size
                        self.total_packets += 1
                        seq_no += 1

                    if self.pkg_data == "None" and self.printpkg:
                        self.pkg_data = test_data.hex()

                if not self.forced_quit:
                    # 发送FIN包并等待确认
                    for _ in range(40):
                        try:
                            fin_packet = UDPPacket(UDPPacket.TYPE_FIN, int(time.time() * 1000000), self.total_packets)
                            self.socket.sendto(fin_packet.to_bytes(), (self.host, self.port))
                            
                            self.socket.settimeout(0.1)
                            data, _ = self.socket.recvfrom(65535)
                            packet = UDPPacket.from_bytes(data)
                            if packet.seq_no == UDPPacket.TYPE_FIN_ACK:
                                self.total_received_packets = packet.total_packets
                                break
                        except socket.timeout:
                            continue

            except KeyboardInterrupt:
                self.forced_quit = True
                for _ in range(10):
                    # 发送强制退出信号给服务器
                    quit_packet = UDPPacket(UDPPacket.TYPE_FORCE_QUIT, int(time.time() * 1000000), total_packets=self.total_packets)
                    self.socket.sendto(quit_packet.to_bytes(), (self.host, self.port))
                    # 等待确认
                    try:
                        self.socket.settimeout(0.1)
                        data, _ = self.socket.recvfrom(65535)
                        packet = UDPPacket.from_bytes(data)
                        if packet.seq_no == UDPPacket.TYPE_FORCE_QUIT_ACK:
                            self.total_received_packets = packet.total_packets
                            break
                    except socket.timeout:
                        continue

            self.is_running = False
            self.test_end_time = time.time()
            
            if self.stats_thread:
                self.stats_thread.join()

            self.print_summary()

        except Exception as e:
            print(f"Client error: {e}")
        finally:
            if self.socket:
                self.socket.close()