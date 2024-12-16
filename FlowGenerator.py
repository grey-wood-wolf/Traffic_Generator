import socket
import time
import numpy as np
import struct
import json

# 定义无穷
INF = float('inf')

class FlowGenerator:
    def __init__(self, bind_address, host, port, mode, duration=None, total_size=None, packet_size=None, bandwidth=None,
                 interval=1, distributed_packets_per_second=None, distributed_packet_size=None,
                 distributed_bandwidth=None, bandwidth_reset_interval=None, json=False, one_test=False):
        self.bind_address = bind_address
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
        self.max_seq_no = 0
        self.is_running = False
        self.start_time = None
        self.socket = None
        self.stats_thread = None
        self.json = json
        self.one_test = one_test
        
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
        last_max_seq_no = 0
        last_jitters = 0
        self.json_info = {"intervals":[], "end":{}}

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
                if self.type == 'udp' and self.mode == 'server':
                    jitters_diff = self.total_jitters - last_jitters
                    real_sent_packets_diff = self.max_seq_no - last_max_seq_no
                
                # 记录统计数据
                interval_stats = {
                    'times': f'{begin_time:.2f}-{end_time:.2f}', 
                    'bytes': bytes_diff,
                    'bandwidth': current_bandwidth * 1000000,
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
                elif self.type == 'udp' and self.mode == 'server':
                    lost_packets = real_sent_packets_diff - packets_diff
                    lost_percent = 100 * (lost_packets / real_sent_packets_diff if real_sent_packets_diff > 0 else 0)
                    avg_jitter = jitters_diff / packets_diff if packets_diff > 0 else 0
                    interval_stats.update({
                        'lost_packets': lost_packets,  # 丢包数
                        'lost_percent': lost_percent,  # 丢包率
                        'jitter_ms': avg_jitter,    # 平均抖动
                    })


                self.interval_data.append(interval_stats)
                if self.json:
                    self.json_info["intervals"].append(interval_stats)
                else:
                    if self.type == 'tcp' and self.mode == 'client':
                        print(f"[ {begin_time:.2f}-{end_time:.2f} s]  "
                            f"Transfer: {bytes_diff/(1024*1024):.2f} MB  "
                            f"Bandwidth: {current_bandwidth:.2f} Mbps  "
                            f"Cwnd: {cwnd}  "
                            f"Retr: {retr}  "
                            f"RTT: {rtt:.2f}  ")
                    elif self.type == 'tcp' and self.mode == 'server':
                        print(f"[ {begin_time:.2f}-{end_time:.2f} s]  "
                            f"Received: {bytes_diff/(1024*1024):.2f} MB  "
                            f"Bandwidth: {current_bandwidth:.2f} Mbps  ")
                    elif self.type == 'udp' and self.mode == 'client':
                        print(f"[ {begin_time:.2f}-{end_time:.2f} s]  "
                            f"Transfer: {bytes_diff/(1024*1024):.2f} MB  "
                            f"Bandwidth: {current_bandwidth:.2f} Mbps  "
                            f"Total Datagrams: {packets_diff}  ")
                    elif self.type == 'udp' and self.mode == 'server':
                        print(f"[ {begin_time:.2f}-{end_time:.2f} s]  "
                            f"Transfer: {bytes_diff/(1024*1024):.2f} MB  "
                            f"Bitrate: {current_bandwidth:.2f} Mbps  "
                            f"Jitters: {avg_jitter:.3f} ms  "
                            f"Lost/Total Datagrams: {lost_packets}/{real_sent_packets_diff} ({lost_percent:.0f}%)  ")
                    else:
                        print(f"[ {begin_time:.2f}-{end_time:.2f} s]  "
                            f"Transfer: {bytes_diff/(1024*1024):.2f} MB  "
                            f"Bandwidth: {current_bandwidth:.2f} Mbps  ")
                
                last_bytes = last_bytes + bytes_diff
                last_packets = last_packets + packets_diff
                last_time = last_time + self.interval
                if self.type == 'udp' and self.mode == 'server':
                    last_jitters = last_jitters + jitters_diff
                    last_max_seq_no = last_max_seq_no + real_sent_packets_diff
            if not self.is_running:
                break

    def print_summary(self):
        """打印测试总结"""
        if not self.interval_data:
            return
        
        test_duration = self.test_end_time - self.test_start_time
        avg_bandwidth = (self.total_sent * 8) / (test_duration * 1000 * 1000) if self.total_sent > 0 else 0
        
        if self.json:
            sum_info = {"start": self.test_start_time, 
                        "end": self.test_end_time, 
                        "seconds": test_duration,
                        "bytes": self.total_sent,
                        "bits_per_second": avg_bandwidth * 1000000,
                    }
        else:
            print("\n=== Test Summary ===")
            print(f"Duration: {test_duration:.2f} seconds")
            print(f"Total Data: {self.total_sent/(1024*1024):.2f} MB")
            print(f"Average Bandwidth: {avg_bandwidth:.2f} Mbps")
        if self.type == 'tcp' and self.mode == 'client':
            if self.json:
                sum_info["max_snd_cwnd"] = max([x['cwnd'] for x in self.interval_data])
                sum_info["mean_rtt"] = np.mean([x['rtt'] for x in self.interval_data])
                sum_info["retransmits"] = self.retr
            else:
                print(f"Max_cwnd: {max([x['cwnd'] for x in self.interval_data])} bytes")
                print(f"Mean_RTT: {np.mean([x['rtt'] for x in self.interval_data]):.2f}") 
                print(f"Retransmissions: {self.retr}")
        elif self.type == 'udp' and self.mode == 'server':
            lost_packets = self.total_sent_packets - self.total_packets
            avg_jitter = self.total_jitters / self.total_packets if self.total_packets > 0 else 0
            if self.json:
                sum_info["lost_packets"] = lost_packets
                sum_info["lost_percent"] = 100 * (lost_packets / self.total_sent_packets)
                sum_info["jitter_ms"] = avg_jitter
            else:
                print("Jitters: {:.3f} ms".format(avg_jitter))
                print(f"Lost/Total Datagrams: {lost_packets}/{self.total_sent_packets} ({lost_packets/self.total_sent_packets*100:.0f}%)")
        elif self.type == 'udp' and self.mode == 'client':
            lost_packets = self.total_packets - self.total_received_packets
            if self.json:
                sum_info["lost_packets"] = lost_packets
                sum_info["lost_percent"] = 100 * (lost_packets / self.total_packets)
            else:
                print(f"Lost/Total Datagrams: {lost_packets}/{self.total_packets} ({lost_packets/self.total_packets*100:.0f}%)")

        if self.json:
            self.json_info["end"] = sum_info
            print(json.dumps(self.json_info, indent=4))
        self.json_info = {}