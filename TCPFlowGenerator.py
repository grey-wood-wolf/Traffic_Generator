import socket
import time
import threading

from FlowGenerator import FlowGenerator

class TCPFlowGenerator(FlowGenerator):
    def __init__(self, bind_address, host, port, mode, duration=None, total_size=None, packet_size=None, bandwidth=None,
                    interval=1, distributed_packets_per_second=None, distributed_packet_size=None,
                    distributed_bandwidth=None, bandwidth_reset_interval=None, json=False, one_test=False, ipv6=False):
        if packet_size is None:
            if bandwidth is not None:
                bandwidth = self.to_bps(bandwidth)
                packet_size = min(64000, int(bandwidth * 0.005) )
            else:
                packet_size = 64000
            packet_size = max(80, packet_size)
        super().__init__(bind_address, host, port, mode, duration, total_size, packet_size, bandwidth, interval,
                        distributed_packets_per_second, distributed_packet_size, distributed_bandwidth,
                        bandwidth_reset_interval, json, one_test, ipv6)
        self.type = 'tcp'

    def run_server(self):
        try:
            if not self.bind_address:
                self.bind_address = '0.0.0.0' if not self.ipv6 else '::'
            socket_family = socket.AF_INET6 if self.ipv6 else socket.AF_INET
            server_socket = socket.socket(socket_family, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.bind_address, self.port))
            server_socket.listen(1)
            if not self.json:
                print(f"TCP Server listening on {self.bind_address}:{self.port}")

            while True:
                client_socket, address = server_socket.accept()
                if not self.json:
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
                    
                    if self.one_test:
                        break

        except Exception as e:
            print(f"Server error: {e}")
        finally:
            server_socket.close()

    def run_client(self):
        try:
            socket_family = socket.AF_INET6 if self.ipv6 else socket.AF_INET
            self.socket = socket.socket(socket_family, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 0)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 0)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            if not self.json:
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
        except KeyboardInterrupt:
            self.is_running = False
            self.test_end_time = time.time()
            
            if self.stats_thread:
                self.stats_thread.join()

            self.print_summary()
        finally:
            if self.socket:
                self.socket.close()
