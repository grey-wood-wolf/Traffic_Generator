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
    def __init__(self, host, port, mode, duration=None, total_size=None, packet_size=None, bandwidth=None,
                 interval=1, distributed_packets_per_second=None, distributed_packet_size=None,
                 distributed_bandwidth=None, bandwidth_reset_interval=None, json=False, one_test=False):
        if bandwidth is None:
            bandwidth = "1M"
        if packet_size is None:
            packet_size = 1450
        super().__init__(host, port, mode, duration, total_size, packet_size, bandwidth, interval,
                         distributed_packets_per_second, distributed_packet_size, distributed_bandwidth,
                         bandwidth_reset_interval, json, one_test)
        self.type = 'udp'
        
    def create_test_data(self, seq_no):
        payload_size = self.packet_size - 16  # 减去包头大小
        test_data = b'x' * payload_size
        packet = UDPPacket(seq_no, int(time.time() * 1000000), 0, test_data)
        return packet.to_bytes()

    def run_server(self):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            server_socket.bind((self.host, self.port))
            print(f"UDP Server listening on {self.host}:{self.port}")

            while True:
                # 等待客户端发起连接
                print("Waiting for client connection...")
                while True:
                    data, addr = server_socket.recvfrom(65535)
                    packet = UDPPacket.from_bytes(data)
                    if packet.seq_no == UDPPacket.TYPE_INIT:
                        # 发送确认包
                        ack_packet = UDPPacket(UDPPacket.TYPE_INIT_ACK, int(time.time() * 1000000))
                        server_socket.sendto(ack_packet.to_bytes(), addr)
                        break
                
                print("Client connected, starting test...")
                self.received_packets_seq_no = set()
                self.total_sent = 0
                self.total_packets = 0
                self.max_seq_no = 0         # 最大的包序列号
                self.total_jitters = 0       # 总抖动
                
                self.is_running = True
                self.test_start_time = self.start_time = time.time()
                
                self.stats_thread = threading.Thread(target=self.print_statistics)
                self.stats_thread.daemon = True
                self.stats_thread.start()
                
                self.total_sent_packets = 0
                last_transit = 0
                
                while self.is_running:
                    try:
                        data, addr = server_socket.recvfrom(65535)
                        packet = UDPPacket.from_bytes(data)
                        
                        if packet.seq_no == UDPPacket.TYPE_FIN:
                            self.total_sent_packets = packet.total_packets
                            ack_packet = UDPPacket(UDPPacket.TYPE_FIN_ACK, int(time.time() * 1000000), self.total_packets)
                            server_socket.sendto(ack_packet.to_bytes(), addr)
                            break
                            
                        self.max_seq_no = max(self.max_seq_no, packet.seq_no)
                        self.total_sent += len(data)
                        self.total_packets += 1
                        transit = (time.time() - packet.timestamp / 1000000) * 1000 # 单位ms
                        self.total_jitters += abs(transit - last_transit)
                        last_transit = transit

                    except Exception as e:
                        print(f"Error receiving data: {e}")
                        break
                
                self.is_running = False
                self.test_end_time = time.time()
                if self.stats_thread:
                    self.stats_thread.join()
                
                if self.total_sent > 0:
                    self.print_summary()
                
                if self.one_test:
                    break

        except Exception as e:
            print(f"Server error: {e}")
        finally:
            server_socket.close()

    def run_client(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            print(f"UDP Client connecting to {self.host}:{self.port}")
            
            # 发送建立连接请求
            for _ in range(10):  # 重试3次
                try:
                    init_packet = UDPPacket(UDPPacket.TYPE_INIT, int(time.time() * 1000000))
                    self.socket.sendto(init_packet.to_bytes(), (self.host, self.port))
                    
                    self.socket.settimeout(0.1)
                    data, _ = self.socket.recvfrom(65535)
                    packet = UDPPacket.from_bytes(data)
                    if packet.seq_no == UDPPacket.TYPE_INIT_ACK:
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

            if self.pps:
                next_send_time = time.time()

            while True:
                if self.duration and time.time() - self.start_time >= self.duration:
                    break
                if self.total_size and self.total_sent >= self.total_size:
                    break

                if time.time() - last_reset_time >= self.bandwidth_reset_interval:
                    self.reset_bandwidth()
                    last_reset_time = time.time()
                    
                try:
                    if self.pps:
                        current_time = time.time()
                        while True:
                            if current_time > next_send_time:
                                test_data = self.create_test_data(seq_no)
                                self.socket.sendto(test_data, (self.host, self.port))
                                self.total_sent += len(test_data)
                                self.total_packets += 1
                                seq_no += 1
                                next_send_time += self.return_packet_interval()
                            else:
                                break
                    else:
                        test_data = self.create_test_data(seq_no)
                        self.socket.sendto(test_data, (self.host, self.port))
                        self.total_sent += len(test_data)
                        self.total_packets += 1
                        seq_no += 1
                            
                except socket.error as e:
                    print(f"Send error: {e}")
                    break

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
