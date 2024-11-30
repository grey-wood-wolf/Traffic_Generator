#!/usr/bin/env python3
import socket
import time
import threading
import argparse
import numpy as np
import sys
import json
from datetime import datetime
import struct

# 定义无穷
INF = float('inf')

class FlowGenerator:
    def __init__(self, host, port, duration=None, total_size=None, packet_size=None, bandwidth=None,
                 interval=1, distributed_packets_per_second=None, distributed_packet_size=None,
                 distributed_bandwidth=None, bandwidth_reset_interval=None, json=False, one_test=False):
        self.host = host
        self.port = port
        self.duration = duration
        self.total_size = self.to_bytes(total_size)  # 总大小
        self.packet_size = packet_size  # 包大小
        self.bandwidth = self.to_bps(bandwidth)  # 带宽限制
        self.pps = None if self.bandwidth is None else int(self.bandwidth / (packet_size * 8))
        self.interval = interval  # 统计间隔
        self.dist_pps = distributed_packets_per_second  
        self.dist_len = distributed_packet_size  
        self.dist_bw = distributed_bandwidth
        self.bandwidth_reset_interval = bandwidth_reset_interval if bandwidth_reset_interval else INF
        self.mean_pkt_interval = 1.0 / self.pps if self.pps else None
        
        self.total_sent = 0
        self.total_packets = 0
        self.is_running = False
        self.start_time = None
        self.socket = None
        self.stats_thread = None
        
        # 存储统计数据
        self.interval_data = []
        self.test_start_time = None
        self.test_end_time = None

    def to_bps(self, value):
        if value is None:
            return None
        if type(value) != str:
            return value
        if value[-1] in ['K', 'k']:
            return int(value[:-1]) * 1000
        if value[-1] in ['M', 'm']:
            return int(value[:-1]) * 1000 * 1000
        if value[-1] in ['G', 'g']:
            return int(value[:-1]) * 1000 * 1000 * 1000
        return int(value)

    def to_bytes(self, value):
        if value is None:
            return None
        if type(value) != str:
            return value
        if value[-1] in ['K', 'k']:
            return int(value[:-1]) * 1024
        if value[-1] in ['M', 'm']:
            return int(value[:-1]) * 1024 * 1024
        if value[-1] in ['G', 'g']:
            return int(value[:-1]) * 1024 * 1024 * 1024
        return int(value)

    def reset_bandwidth(self):
        if self.dist_bw == None:
            return
        if self.dist_bw == 'exp' and self.bandwidth != None:
            bandwidth = int(np.random.exponential(self.bandwidth))
            self.pps = int(bandwidth / (self.packet_size * 8))
            self.mean_pkt_interval = 1.0 / self.pps 
        else:
            raise ValueError("Unsupported bandwidth distribution")

    def create_test_data(self):
        if self.dist_len == None:
            return b'X' * self.packet_size
        if self.dist_len == 'exp':
            return b'X' * min(int(np.random.exponential(self.packet_size)), 64000)
        else:
            raise ValueError("Unsupported packet size distribution")
    
    def return_packet_interval(self):
        if self.dist_pps == None:
            return self.mean_pkt_interval
        if self.dist_pps == 'exp':
            return np.random.exponential(self.mean_pkt_interval)
        else:
            raise ValueError("Unsupported packet interval distribution")

    def print_statistics(self):
        last_bytes = 0
        last_packets = 0
        last_time = self.start_time
        start_time = time.time()

        while True:
            current_time = time.time()
            time.sleep(0.01)
            if current_time - last_time > self.interval or not self.is_running:
                interval_time = current_time - last_time
                begin_time = last_time - start_time
                end_time = current_time - start_time
                
                bytes_diff = self.total_sent - last_bytes
                packets_diff = self.total_packets - last_packets
                current_bandwidth = (bytes_diff * 8) / (interval_time * 1000 * 1000)  # Mbps
                current_pps = packets_diff / interval_time
                
                # 记录统计数据
                interval_stats = {
                    'times': f'{end_time:.2f}-{begin_time:.2f}', 
                    'bytes': bytes_diff,
                    'bandwidth_mbps': current_bandwidth,
                    'packets': packets_diff,
                    'pps': current_pps,
                    'total_bytes': self.total_sent,
                    'total_packets': self.total_packets
                }
                self.interval_data.append(interval_stats)
                
                print(f"[{end_time:.2f}-{begin_time:.2f} s]  "
                    f"Interval: {bytes_diff/(1024*1024):.2f} MB  "
                    f"Bandwidth: {current_bandwidth:.2f} Mbps  "
                    f"Packets: {packets_diff}  "
                    f"PPS: {current_pps:.2f}")
                
                last_bytes = self.total_sent
                last_packets = self.total_packets
                last_time = current_time
            if not self.is_running:
                break
    def print_summary(self):
        """打印测试总结"""
        if not self.interval_data:
            return
        
        test_duration = self.test_end_time - self.test_start_time
        avg_bandwidth = (self.total_sent * 8) / (test_duration * 1000 * 1000) if self.total_sent > 0 else 0
        avg_pps = self.total_packets / test_duration if self.total_packets > 0 else 0
        
        print("\n=== Test Summary ===")
        print(f"Duration: {test_duration:.2f} seconds")
        print(f"Total Data: {self.total_sent/(1024*1024):.2f} MB")
        print(f"Total Packets: {self.total_packets}")
        print(f"Average Bandwidth: {avg_bandwidth:.2f} Mbps")
        print(f"Average PPS: {avg_pps:.2f}")
        
class TCPFlowGenerator(FlowGenerator):
    def __init__(self, host, port, duration=None, total_size=None, packet_size=None, bandwidth=None,
                    interval=1, distributed_packets_per_second=None, distributed_packet_size=None,
                    distributed_bandwidth=None, bandwidth_reset_interval=None, json=False, one_test=False):
        if packet_size is None:
            packet_size = 64000
        super().__init__(host, port, duration, total_size, packet_size, bandwidth, interval,
                        distributed_packets_per_second, distributed_packet_size, distributed_bandwidth,
                        bandwidth_reset_interval, json, one_test)

    def run_server(self):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.host, self.port))
            server_socket.listen(1)
            print(f"TCP Server listening on {self.host}:{self.port}")

            while True:
                client_socket, address = server_socket.accept()
                print(f"Connection from {address}")
                
                self.total_sent = 0
                self.total_packets = 0
                self.interval_data = []
                
                self.is_running = True
                self.test_start_time = self.start_time = time.time()
                
                # 启动统计信息打印线程
                self.stats_thread = threading.Thread(target=self.print_statistics)
                self.stats_thread.daemon = True
                self.stats_thread.start()
                
                try:
                    while True:
                        data = client_socket.recv(65535)
                        if not data:
                            break
                        self.total_sent += len(data)
                        self.total_packets += 1

                except Exception as e:
                    print(f"Error receiving data: {e}")
                finally:
                    self.is_running = False
                    self.test_end_time = time.time()
                    if self.stats_thread:
                        self.stats_thread.join()
                    client_socket.close()
                    if self.total_sent > 0:
                        self.print_summary()

        except Exception as e:
            print(f"Server error: {e}")
        finally:
            server_socket.close()

    def run_client(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 0)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 0)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            print(f"Connected to {self.host}:{self.port}")
            
            self.is_running = True
            self.test_start_time = self.start_time = time.time()
            last_reset_time = self.start_time
            
            self.stats_thread = threading.Thread(target=self.print_statistics)
            self.stats_thread.daemon = True
            self.stats_thread.start()

            self.reset_bandwidth()

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
                                test_data = self.create_test_data()
                                self.socket.sendall(test_data)
                                self.total_sent += len(test_data)
                                self.total_packets += 1
                                next_send_time += self.return_packet_interval()
                            else:
                                break
                    else:
                        test_data = self.create_test_data()
                        self.socket.sendall(test_data)
                        self.total_sent += len(test_data)
                        self.total_packets += 1
                            
                except socket.error as e:
                    print(f"Send error: {e}")
                    break

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

class UDPPacket:
    # 添加包类型常量
    TYPE_INIT = 0xFFFFFFF0  # 建立连接请求
    TYPE_INIT_ACK = 0xFFFFFFF1  # 建立连接确认
    TYPE_DATA = 0x0  # 普通数据包
    TYPE_FIN = 0xFFFFFFFF  # 结束包
    TYPE_FIN_ACK = 0xFFFFFFFE  # 结束确认包

    def __init__(self, seq_no, timestamp, total_sent_packets=0, data=b''):
        self.seq_no = seq_no
        self.timestamp = timestamp
        self.total_sent_packets = total_sent_packets
        self.data = data
        
    def to_bytes(self):
        header = struct.pack('!IQI', self.seq_no, self.timestamp, self.total_sent_packets)
        return header + self.data
        
    @staticmethod
    def from_bytes(data):
        header = data[:16]  # 4+8+4=16字节的包头
        seq_no, timestamp, total_sent_packets = struct.unpack('!IQI', header)
        return UDPPacket(seq_no, timestamp, total_sent_packets, data[16:])

class UDPFlowGenerator(FlowGenerator):
    def __init__(self, host, port, duration=None, total_size=None, packet_size=None, bandwidth=None,
                 interval=1, distributed_packets_per_second=None, distributed_packet_size=None,
                 distributed_bandwidth=None, bandwidth_reset_interval=None, json=False, one_test=False):
        if bandwidth is None:
            bandwidth = "1M"
        if packet_size is None:
            packet_size = 1450
        super().__init__(host, port, duration, total_size, packet_size, bandwidth, interval,
                         distributed_packets_per_second, distributed_packet_size, distributed_bandwidth,
                         bandwidth_reset_interval, json, one_test)
        self.received_packets = {}  # 记录收到的包序列号
        self.expected_seq_no = 0    # 期望的下一个序列号
        self.duplicates = 0         # 重复包数量
        
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
                self.received_packets.clear()
                self.duplicates = 0
                self.total_sent = 0
                self.total_packets = 0
                
                self.is_running = True
                self.test_start_time = self.start_time = time.time()
                
                self.stats_thread = threading.Thread(target=self.print_statistics)
                self.stats_thread.daemon = True
                self.stats_thread.start()
                
                total_sent_packets = 0
                
                while self.is_running:
                    try:
                        data, addr = server_socket.recvfrom(65535)
                        packet = UDPPacket.from_bytes(data)
                        
                        if packet.seq_no == UDPPacket.TYPE_FIN:
                            total_sent_packets = packet.total_sent_packets
                            ack_packet = UDPPacket(UDPPacket.TYPE_FIN_ACK, int(time.time() * 1000000))
                            server_socket.sendto(ack_packet.to_bytes(), addr)
                            break
                            
                        if packet.seq_no in self.received_packets:
                            self.duplicates += 1
                        else:
                            self.received_packets[packet.seq_no] = packet
                        
                        self.total_sent += len(data)
                        self.total_packets += 1

                    except Exception as e:
                        print(f"Error receiving data: {e}")
                        break
                
                self.is_running = False
                self.test_end_time = time.time()
                if self.stats_thread:
                    self.stats_thread.join()
                
                if total_sent_packets > 0:
                    lost_packets = total_sent_packets - len(self.received_packets)
                    loss_rate = (lost_packets / total_sent_packets * 100)
                    
                    print(f"\nFinal Statistics:")
                    print(f"Total Sent Packets: {total_sent_packets}")
                    print(f"Received Packets: {len(self.received_packets)}")
                    print(f"Lost Packets: {lost_packets}")
                    print(f"Loss Rate: {loss_rate:.2f}%")
                    print(f"Duplicates: {self.duplicates}")
                
                if self.total_sent > 0:
                    self.print_summary()

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
            seq_no = 0

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

def main():
    parser = argparse.ArgumentParser(description='TCP/UDP Flow Generator')
    parser.add_argument('-s', '--server', action='store_true', help='Run as server')
    parser.add_argument('-c', '--client', help='Server IP address to connect to')
    parser.add_argument('-p', '--port', type=int, default=5001, help='Port number')
    parser.add_argument('-u', '--udp', action='store_true', help='Use UDP instead of TCP')
    parser.add_argument('-t', '--time', type=int, help='Test duration in seconds')
    parser.add_argument('-n', '--size', type=str, help='Total size to transfer in MB')
    parser.add_argument('-l', '--packet-size', type=int, help='Packet size in bytes')
    parser.add_argument('-b', '--bandwidth', type=str, help='Bandwidth limit in bps')
    parser.add_argument('-i', '--interval', type=float, default=1.0, help='Statistics interval in seconds')
    parser.add_argument('-dpps', '--distributed_packets_per_second', type=str, help='Distributed packets per second')
    parser.add_argument('-dl', '--distributed_packet-size', type=str, help='Distributed packet size in bytes')
    parser.add_argument('-db', '--distributed_bandwidth', type=str, help='Distributed bandwidth limit in bps')
    parser.add_argument('-bri','--bandwidth_reset_interval', type=float, help='Bandwidth reset interval in seconds')
    parser.add_argument('-J', '--json', action='store_true', help='Print statistics as JSON file')
    parser.add_argument('-1', '--one_test', action='store_true', help='Run only one test')

    args = parser.parse_args()

    if args.time is not None and args.size is not None:
        print("Error: Cannot specify both time and size")
        sys.exit(1)

    # 选择Generator类
    GeneratorClass = UDPFlowGenerator if args.udp else TCPFlowGenerator
    if args.server:
        generator = GeneratorClass('0.0.0.0', args.port, args.time, args.size, 
                               args.packet_size, args.bandwidth, args.interval,
                               args.distributed_packets_per_second, args.distributed_packet_size,
                               args.distributed_bandwidth, args.bandwidth_reset_interval,
                               args.json, args.one_test)
        generator.run_server()
    elif args.client:
        generator = GeneratorClass(args.client, args.port, args.time, args.size,
                               args.packet_size, args.bandwidth, args.interval,
                               args.distributed_packets_per_second, args.distributed_packet_size,
                               args.distributed_bandwidth, args.bandwidth_reset_interval,
                               args.json, args.one_test)
        generator.run_client()
    else:
        parser.print_help()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)