import socket
import threading
import queue
import subprocess
import argparse

class UDPHandler:
    def __init__(self, reserve_rate=0.5, new_rate=0.2, new_content='-uestc-'):
        # Debug mode control
        self.DEBUG = False
        # Reserved rate
        self.reserved_rate = reserve_rate
        # New content rate
        self.new_rate = new_rate
        # New content
        self.new_content = new_content
    
    def handle(self, data):
        original_length = len(data)
        cut_length = int(original_length * self.reserved_rate)  
        custom_length = int(original_length * self.new_rate)  
        
        truncated_data = data[:cut_length]  # Truncate original data
        # Generate custom content (can be modified as needed)
        custom_data = self.new_content.encode() * (custom_length // len(self.new_content))  # Repeat custom content to fill the length
        if len(custom_data) < custom_length:
            custom_data += self.new_content.encode()[:custom_length - len(custom_data)]
        # Merge truncated data and custom content
        new_data = truncated_data + custom_data
        if self.DEBUG:
            print(f"Handling data: original length={original_length}, truncated length={cut_length}, custom length={custom_length}")
        return new_data
        
class UDPForwarder:
    def __init__(self, reserve_rate=0.5, new_rate=0.2, new_content='-uestc-'):
        self.udp_handler = UDPHandler(reserve_rate, new_rate, new_content)

class UDPForwarder_426(UDPForwarder):
    def __init__(self, forward_config, handler_config):

        listen_port, ipv6_address, ipv6_port = forward_config['listen_port'], forward_config['target_address'], forward_config['target_port']
        reserve_rate, new_rate, new_content = handler_config['reserve_rate'], handler_config['new_rate'], handler_config['new_content']

        super().__init__(reserve_rate, new_rate, new_content)

        # Debug mode control
        self.DEBUG = False
        
        # IPv4 listening configuration
        self.ipv4_port = listen_port

        # Target address setting
        self.ipv6_address = ipv6_address
        self.ipv6_port = ipv6_port

        # Client sessions {client ID: session info}
        self.sessions = {}

        # Create main IPv4 listening socket
        self.sock_ipv4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_ipv4.bind(('0.0.0.0', self.ipv4_port))

    def start(self):
        try:
            # Main loop - accept new connections and create sessions for each client
            while True:
                data, addr = self.sock_ipv4.recvfrom(65535)
                client_ip, client_port = addr
                
                client_id = f"{client_ip}:{client_port}"
                
                if client_id not in self.sessions:
                    if self.DEBUG:
                        print(f"New client connection: {client_id}")
                    
                    self._create_session(client_ip, client_port, client_id)
                
                self.sessions[client_id]['queue'].put(data)
                
        except KeyboardInterrupt:
            if self.DEBUG:
                print("Forwarder closed")
            self.sock_ipv4.close()
            
    def _create_session(self, client_ip, client_port, client_id):
        """Create a session for a new client"""
        data_queue = queue.Queue()
        
        sock_ipv6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        
        sock_ipv6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock_ipv6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            sock_ipv6.bind(('::', client_port))
            if self.DEBUG:
                print(f"IPv6 socket bound to port: {client_port}")
        except Exception as e:
            if self.DEBUG:
                print(f"IPv6 socket bind error: {e}")
            return None
        
        session = {
            'client_ip': client_ip,
            'client_port': client_port,
            'ipv6_socket': sock_ipv6,
            'queue': data_queue,
            'active': True
        }
        
        self.sessions[client_id] = session
        
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
        """Handle data flow from IPv4 to IPv6"""
        sock_ipv6 = session['ipv6_socket']
        client_ip = session['client_ip']
        client_port = session['client_port']
        
        ipv6_dest = (self.ipv6_address, self.ipv6_port)
        
        try:
            while session['active']:
                try:
                    data = session['queue'].get(timeout=1.0)

                    new_data = self.udp_handler.handle(data)
                    
                    try:
                        sock_ipv6.sendto(new_data, ipv6_dest)
                        if self.DEBUG:
                            print(f"IPv4→IPv6: {client_ip}:{client_port} → [{self.ipv6_address}]:{self.ipv6_port}")
                    except Exception as e:
                        if self.DEBUG:
                            print(f"IPv6 send error: {e}")
                    
                except queue.Empty:
                    continue
                    
        except Exception as e:
            if self.DEBUG:
                print(f"IPv4→IPv6 handler error ({client_id}): {e}")
            session['active'] = False
    
    def _ipv6_to_ipv4_handler(self, session, client_id):
        """Handle data flow from IPv6 to IPv4"""
        sock_ipv6 = session['ipv6_socket']
        client_ip = session['client_ip']
        client_port = session['client_port']

        try:
            sock_ipv6.settimeout(1.0)
            
            while session['active']:
                try:
                    data, addr = sock_ipv6.recvfrom(65535)
                    
                    self.sock_ipv4.sendto(data, (client_ip, client_port))
                    
                    if self.DEBUG:
                        src_addr = f"[{addr[0]}]:{addr[1]}" if len(addr) >= 2 else "Unknown"
                        print(f"IPv6→IPv4: {src_addr} → {client_ip}:{client_port}")
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.DEBUG:
                        print(f"Error handling IPv6 packet: {e}")
        
        except Exception as e:
            if self.DEBUG:
                print(f"IPv6→IPv4 handler error ({client_id}): {e}")
            session['active'] = False

class UDPForwarder_624(UDPForwarder):
    def __init__(self, forward_config, handler_config):

        listen_port, ipv4_address, ipv4_port = forward_config['listen_port'], forward_config['target_address'], forward_config['target_port']
        reserve_rate, new_rate, new_content = handler_config['reserve_rate'], handler_config['new_rate'], handler_config['new_content']

        super().__init__(reserve_rate, new_rate, new_content)

        # Debug mode control
        self.DEBUG = False
        
        # IPv6 listening configuration
        self.ipv6_port = listen_port

        # Target address setting
        self.ipv4_address = ipv4_address
        self.ipv4_port = ipv4_port

        # Client sessions {client ID: session info}
        self.sessions = {}

        # Create main IPv6 listening socket
        self.sock_ipv6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        self.sock_ipv6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        self.sock_ipv6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock_ipv6.bind(('::', self.ipv6_port))

    def start(self):
        try:
            # Main loop - accept new connections and create sessions for each client
            while True:
                data, addr = self.sock_ipv6.recvfrom(65535)
                client_id = f"{addr[0]}%{addr[1]}"  # Use % to separate IPv6 address and port
                
                if client_id not in self.sessions:
                    if self.DEBUG:
                        print(f"New client connection: {client_id}")
                    
                    if self._create_session(addr, client_id) is None:
                        continue
                
                self.sessions[client_id]['queue'].put(data)
                
        except KeyboardInterrupt:
            if self.DEBUG:
                print("Forwarder closed")
            self.sock_ipv6.close()
            
    def _create_session(self, client_addr, client_id):
        """Create a session for a new client"""
        data_queue = queue.Queue()
        
        sock_ipv4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        try:
            sock_ipv4.bind(('0.0.0.0', client_addr[1]))
            if self.DEBUG:
                bound_port = sock_ipv4.getsockname()[1]
                print(f"IPv4 socket bound to port: {bound_port}")
        except Exception as e:
            if self.DEBUG:
                print(f"IPv4 socket bind error: {e}")
            return None
        
        session = {
            'client_addr': client_addr,
            'ipv4_socket': sock_ipv4,
            'queue': data_queue,
            'active': True
        }
        
        self.sessions[client_id] = session
        
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
        """Handle data flow from IPv6 to IPv4"""
        sock_ipv4 = session['ipv4_socket']
        dest_address = (self.ipv4_address, self.ipv4_port)
        
        try:
            while session['active']:
                try:
                    data = session['queue'].get(timeout=1.0)

                    new_data = self.udp_handler.handle(data)
                    
                    try:
                        sock_ipv4.sendto(new_data, dest_address)
                        if self.DEBUG:
                            client_addr = session['client_addr']
                            print(f"IPv6→IPv4: [{client_addr[0]}]:{client_addr[1]} → {dest_address[0]}:{dest_address[1]}")
                    except Exception as e:
                        if self.DEBUG:
                            print(f"IPv4 send error: {e}")
                        session['active'] = False
                    
                except queue.Empty:
                    continue
                    
        except Exception as e:
            if self.DEBUG:
                print(f"IPv6→IPv4 handler error ({client_id}): {e}")
            session['active'] = False
    
    def _ipv4_to_ipv6_handler(self, session, client_id):
        """Handle data flow from IPv4 to IPv6"""
        sock_ipv4 = session['ipv4_socket']
        client_addr = session['client_addr']

        try:
            sock_ipv4.settimeout(1.0)
            
            while session['active']:
                try:
                    data, addr = sock_ipv4.recvfrom(65535)
                    
                    self.sock_ipv6.sendto(data, client_addr)
                    
                    if self.DEBUG:
                        print(f"IPv4→IPv6: {addr[0]}:{addr[1]} → [{client_addr[0]}]:{client_addr[1]}")
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.DEBUG:
                        print(f"Error handling IPv4 packet: {e}")
                    session['active'] = False
        
        except Exception as e:
            if self.DEBUG:
                print(f"IPv4→IPv6 handler error ({client_id}): {e}")
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
        # Start two socat processes
        ipv4_thread = threading.Thread(target=self.start_socat, args=(self.ipv4_command,))
        ipv6_thread = threading.Thread(target=self.start_socat, args=(self.ipv6_command,))

        ipv4_thread.daemon = True
        ipv6_thread.daemon = True

        ipv4_thread.start()
        ipv6_thread.start()

        ipv4_thread.join()
        ipv6_thread.join()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Set Forwarder related parameters")
    
    parser.add_argument('--ipv4_addr', type=str, default='172.17.0.3', help='IPv4 address')
    parser.add_argument('--ipv4_port', type=int, default=5201, help='IPv4 port')
    parser.add_argument('--ipv6_addr', type=str, default='2001:db8::2', help='IPv6 address')
    parser.add_argument('--ipv6_port', type=int, default=5201, help='IPv6 port')
    
    parser.add_argument('--reserve_rate', type=float, default=0.5, help='Reserve rate')
    parser.add_argument('--new_rate', type=float, default=0.2, help='New content rate')
    parser.add_argument('--new_content', type=str, default='-uestc-', help='New content')

    parser.add_argument('-v', '--version', action='store_true', help='Print version')
    
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

        print(10 * '-' + 'Forwarding started' + 10 * '-')
        print(f"IPv4 Address: {ipv4_address}, IPv4 Port: {ipv4_port}")
        print(f"IPv6 Address: {ipv6_address}, IPv6 Port: {ipv6_port}")
        print(f"Reserve Rate: {reserve_rate}, New Rate: {new_rate}, New Content: {new_content}")

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


