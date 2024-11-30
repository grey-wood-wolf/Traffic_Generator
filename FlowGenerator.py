import socket
import time
import numpy as np
import struct

# 定义无穷
INF = float('inf')

class FlowGenerator:
    def __init__(self, host, port, mode, duration=None, total_size=None, packet_size=None, bandwidth=None,
                 interval=1, distributed_packets_per_second=None, distributed_packet_size=None,
                 distributed_bandwidth=None, bandwidth_reset_interval=None, json=False, one_test=False):
        self.mode = mode
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
        start_time = self.start_time
        self.retr = 0

        while True:
            current_time = time.time()
            time.sleep(0.005)
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

                if self.type == 'tcp' and self.mode == 'client':
                    fmt = "B"*7 + "I"*24
                    info = self.socket.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 104)
                    x = struct.unpack(fmt, info)
                    
                    mss = x[26]      # advmss字段
                    cwnd = x[25]     # snd_cwnd字段
                    cwnd = cwnd * mss if cwnd > 0 else 0  # cwnd(字节)
                    retr = x[14] - self.retr  # retrans重传计数
                    self.retr = x[14]
                    rtt = x[22]      # rtt (微秒)

                    interval_stats.update({
                        'cwnd': cwnd,    # cwnd(字节)
                        'retr': retr,    # 重传次数
                        'rtt': rtt,      # RTT(微秒)
                    })

                self.interval_data.append(interval_stats)
                
                if self.type == 'tcp' and self.mode == 'client':
                    print(f"[{end_time:.2f}-{begin_time:.2f} s]  "
                        f"Transfer: {bytes_diff/(1024*1024):.2f} MB  "
                        f"Bandwidth: {current_bandwidth:.2f} Mbps  "
                        f"Cwnd: {cwnd}  "
                        f"Retr: {retr}  "
                        f"RTT: {rtt:.2f}  ")
                else:
                    print(f"[{end_time:.2f}-{begin_time:.2f} s]  "
                        f"Transfer: {bytes_diff/(1024*1024):.2f} MB  "
                        f"Bandwidth: {current_bandwidth:.2f} Mbps  ")
                
                last_bytes = self.total_sent
                last_packets = self.total_packets
                last_time = last_time + self.interval
            if not self.is_running:
                break

    def print_summary(self):
        """打印测试总结"""
        if not self.interval_data:
            return
        
        test_duration = self.test_end_time - self.test_start_time
        avg_bandwidth = (self.total_sent * 8) / (test_duration * 1000 * 1000) if self.total_sent > 0 else 0
            
        print("\n=== Test Summary ===")
        print(f"Duration: {test_duration:.2f} seconds")
        print(f"Total Data: {self.total_sent/(1024*1024):.2f} MB")
        print(f"Average Bandwidth: {avg_bandwidth:.2f} Mbps")
        if self.type == 'tcp' and self.mode == 'client':
            print(f"Max_cwnd: {max([x['cwnd'] for x in self.interval_data])} bytes")
            print(f"Mean_RTT: {np.mean([x['rtt'] for x in self.interval_data]):.2f}") 
            print(f"Retransmissions: {self.retr}")