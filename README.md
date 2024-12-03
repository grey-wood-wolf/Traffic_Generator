# Traffic_Generator

Traffic_Generator 是一个用于生成和模拟 TCP 或 UDP 流量的工具。该工具可以配置为服务器或客户端模式，以测试网络的性能和稳定性。并且最重要的是该工具可用同时<span style="color:red">**指定不同分布的包间隔、包大小、带宽大小**</span>。以下是可配置的参数及其说明：

## 参数

- `-s`, `--server`: 以服务器模式运行。该模式下，工具会监听指定的端口并等待连接。
- `-c`, `--client`: 客户端模式下，需要指定服务器的 IP 地址。
- `-p`, `--port`: 指定的服务器端口号，默认为 5001。
- `-u`, `--udp`: 使用 UDP 协议而不是 TCP。
- `-t`, `--time`: 测试持续的时间（秒）。指定后，传输会在达到设定时间后停止。
- `-n`, `--size`: 要传输的总数据量。指定后，传输会在传输指定数据量后停止，单位为byte
- `-l`, `--packet-size`: 每个数据包的大小（byte）。
- `-b`, `--bandwidth`: 带宽限制，单位为 bps（比特每秒）。
- `-i`, `--interval`: 统计显示间隔（秒），默认为 1 秒。
- `-dpps`, `--distributed_packets_per_second`: 数据包间隔的分布模式，如exp（指数分布等）。
- `-dl`, `--distributed_packet-size`: 数据包大小分布模式。
- `-db`, `--distributed_bandwidth`: 带宽大小分布模式，配合-bri使用。
- `-bri`, `--bandwidth_reset_interval`: 带宽重置间隔（秒）。在此间隔后，带宽限制将重置。
- `-J`, `--json`: 输出统计数据为 JSON 文件格式。
- `-1`, `--one_test`: 只运行一次测试。
- `-B`, `--bind_address`: 本端绑定的地址。


## 示例
进入文件夹
```bash。
cd ./Traffic_Generator
```

### 服务器端
```bash
python3 main.py -s -p 5001  -u -B 192.168.100.86 -J
```
运行服务器程序，以服务器进行运行，监听端口 5001，接收 udp 流量，绑定本地 ip 为 192.168.100.86，最后结果以json格式进行输出。

### 客户端
```bash
python3 main.py -c 192.168.100.86 -n 1G -b 100M -l 1450 -u -J -dpps exp -dl exp -db exp -bri 1
```
运行客户端程序，以客户端进行运行，指定服务器 ip 地址为 192.168.100.86，发送总数据量 1Gbytes，带宽限制为 100Mbps ，包大小为 1450bytes， 发送 udp 流量，结果以json格式输出，包间隔为指数分布，包大小为指数分布，带宽每 1s 变化一次，并且呈现指数分布。
## 目前不足
由于不支持dpdk技术，因此流量生成速率上限较小，TCP一般为500Mbps，UDP一般为8GMbps。