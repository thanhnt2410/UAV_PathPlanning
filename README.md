# UAV_PathPlanning

Bộ khung nhỏ cho người dùng **tự xây GUI và viết thuật toán lập đường bay**.
Một UAV, Python 3.10+, MAVSDK, Qt/PyQt5, Leaflet và Docker/PX4 Gazebo.
Không cần ROS cho ứng dụng này.

## Clone

```bash
git clone --recurse-submodules --shallow-submodules https://github.com/thanhnt2410/UAV_PathPlanning.git
cd UAV_PathPlanning
```

Nếu đã clone, từ thư mục repository:

```bash
git submodule update --init --recursive
```

Repository này có lịch sử Git mới, chỉ chứa bộ khung basic; không mang lịch sử
model/log từ SW-UAV. PX4 vẫn là submodule và có dung lượng riêng lớn.
Không dùng `--remote` để tự nâng phiên bản PX4.

## Thiết lập Docker lần đầu

Ubuntu 22.04 với giao diện X11/XWayland. Gazebo và Python chạy trong container;
không cần cài Gazebo, Conda hoặc ROS trên host.

Nếu chưa có Docker:

```bash
bash cmd/install_docker.sh
```

Đăng xuất/đăng nhập để cập nhật group Docker, sau đó build và khởi động container:

```bash
cd docker
docker compose up -d --build
```

Chỉ thực hiện lại bước build image khi đổi Dockerfile hoặc requirements.
Nếu đang có container `sw-uav` từ bản SW-UAV đầy đủ, dừng mô phỏng/app và xóa
container cũ trước khi chạy Compose trên nhánh này. Dữ liệu repository được
mount từ host, không nằm trong image.

Vào container từ host:

```bash
xhost +local:docker
```

```bash
docker exec -it sw-uav zsh
```

Build PX4 một lần trong container:

```bash
cd /app/dependencies/PX4-Autopilot
make px4_sitl
```

## Chạy chương trình hằng ngày

Container `sw-uav` đã chạy. Nếu container còn nhưng đã dừng, trên host chạy
`docker start sw-uav` trước khi dùng. Không cần build lại image.

### Terminal 1: một UAV SITL

Trên host:

```bash
xhost +local:docker
```

```bash
docker exec -it sw-uav zsh
```

Trong container:

```bash
cd /app/dependencies/PX4-Autopilot/build/px4_sitl_default/rootfs
PX4_SIM_MODEL=gz_x500 ../bin/px4
```

PX4 khởi động Gazebo cho một model x500. Không chạy thêm Gazebo hoặc script swarm.
Nếu checkout PX4 chưa build plugin Gazebo, lần khởi động đầu dùng
`make -C /app/dependencies/PX4-Autopilot px4_sitl gz_x500` để build và chạy.

### Terminal 2: GUI

Trên host:

```bash
xhost +local:docker
```

```bash
docker exec -it sw-uav zsh
```

Trong container:

```bash
cd /app
python3 src/main.py
```

`src/main.py` là điểm vào chương trình, gọi GUI trong `src/app.py`.
Lệnh `python3 src/app.py` vẫn dùng được.
GUI không tự kết nối hoặc arm. Đa giác mẫu ở vị trí SITL mặc định; click bản đồ
để thêm đỉnh hoặc sửa tọa độ trong panel. Bản đồ nền cần internet.
GUI dùng nguyên bản `assets/map.html` và `assets/map.js`, giữ nguồn Google Hybrid
(ảnh vệ tinh kèm nhãn) của code gốc. `config/interface_config.yaml` chỉ chọn file
HTML; adapter Python nối GUI basic với API map gốc qua `qtWidget`.

1. Chọn **Plan** để so sánh Zigzag và Custom; chọn một dòng kết quả để xem/dùng
   đường tương ứng. Chưa gửi lệnh bay.
2. **Connect**; kiểm tra telemetry, pin, GPS và health.
3. Plan lại nếu muốn dùng vị trí GPS hiện tại làm depot, rồi **Upload**.
4. **Arm** → **Takeoff** → **Start / Resume**, mỗi bước là thao tác riêng.
5. **Pause**, **RTL** hoặc **Land** khi cần. Đường đã upload kết thúc bằng RTL.
6. Hạ cánh và **Disarm** trước khi đóng ứng dụng. Dừng PX4 bằng `Ctrl+C`
   tại terminal 1. Thoát shell không xóa container.

CSV mission dùng `latitude,longitude,altitude` (altitude tương đối, mét), không
header. **Load CSV / Save CSV** để dùng waypoint từ thuật toán ngoài. Upload
vẫn kiểm tra tọa độ, số điểm, altitude và phạm vi theo cấu hình.

## Kết quả thuật toán và mô hình năng lượng

Bảng dưới bản đồ hiển thị từng thuật toán: số waypoint, quãng đường, số lần rẽ,
chi phí, độ phủ, chồng lấn, diện tích quét danh định, thời gian lập đường,
thời gian/năng lượng dự đoán và Score. Chọn dòng để đổi đường đang xem;
**Upload** dùng đúng đường đang chọn. Mặc định chọn chi phí hình học thấp nhất.
Lỗi của một thuật toán được ghi ở tooltip/log; các thuật toán còn lại vẫn chạy.

- `Cost = distance_m + turn_penalty_m × turns`, không tính góc tại depot.
- Coverage là phần đa giác được phủ bởi các dải quét, chia cho diện tích đa giác.
- Overlap là diện tích quét dư do quét lặp, chia cho tổng diện tích các dải trong
  vùng khảo sát. Diện tích quét danh định là `distance × footprint width`, gồm
  cả phần ngoài vùng và quét lặp. Nhập footprint đúng với camera/độ cao đang dùng.
- `Plan (ms)` là thời gian lập đường, khác `Time est. (s)` là thời gian bay dự đoán.
- `Score = Cost + time_weight × Time est. + energy_weight × Energy est.`.
  Đây là điểm so sánh; không phải hàm mục tiêu bắt buộc của thuật toán người dùng.

Bản basic đọc lại **hai model hồi quy đã huấn luyện**, mặc định:

```text
models/mission_energy/total_flight_energy_wh_linear.pkl
models/mission_energy/total_flight_time_s_linear.pkl
```

Đổi thư mục và tên model tại `energy_model` trong `config/uav_config.yaml`.
Input giữ đúng mô hình cũ: `total_distance_m` và `stop_count`; với đường kín,
`stop_count = số waypoint - 1` (bỏ depot đầu, tính điểm quay về).
Chỉ dùng file pickle do bạn huấn luyện hoặc tin cậy. Model/log vẫn được ignore,
không đưa vào Git; người clone repo cần tự cung cấp các file model.

Thiếu model, sai dependency/schema hoặc dự đoán không hợp lệ: Energy, Time est.
và Score hiện **N/A**, có lý do ở tooltip/log; vẫn lập/vẽ đường và hiện các chỉ
số hình học. Không thay bằng 0 hoặc mô hình vật lý khác.

Năng lượng/thời gian là **dự đoán hồi quy**, không phải số đo khi bay SITL.
Model cũ có thể được thu với tốc độ, dwell, pin/motor và khối lượng khác cấu
hình basic; cần đánh giá/huấn luyện lại trước khi dùng để so sánh năng lượng.
Coverage dùng dải quét hình học, chưa chứng minh chất lượng ảnh/phủ thực tế.

## Tự viết thuật toán và GUI

- Thay `plan_path(points, start)` trong [path_algorithms.py](src/planning/path_algorithms.py).
  Trả lại đúng các điểm khảo sát, mỗi điểm một lần. Planner kiểm tra kết quả và
  thêm depot ở hai đầu. Dòng **Custom** chạy hàm này; mặc định nó gọi Zigzag
  nên hai dòng có thể giống nhau. Thêm hàm vào `get_algorithms()` để hiện thêm
  thuật toán trong bảng, không cần sửa GUI.
- Thay layout trong [interface_base.py](src/interface_base.py), nối thao tác
  trong [main_controller.py](src/main_controller.py). Service không phụ thuộc Qt,
  có thể dùng lại từ GUI khác.
- Cấu hình endpoint, spacing, altitude, tốc độ và giới hạn trong
  [uav_config.yaml](config/uav_config.yaml). Không bỏ qua safety checks để chạy demo.
- Vị trí ban đầu của một UAV nằm trong [init_pos_uavs.yaml](config/init_pos_uavs.yaml),
  dùng cho bản đồ và lập đường offline; khi kết nối dùng GPS thực của UAV.
  File này không thay đổi vị trí spawn của SITL.
- Giữ [interface_config.yaml](config/interface_config.yaml) để cấu hình bản đồ và
  [stream_config.yaml](config/stream_config.yaml) để mở rộng video sau này (basic
  chưa có stream). Chỉ rút gọn dữ liệu bên trong config, không xóa file.

Chi tiết luồng dữ liệu và hợp đồng mở rộng:
[PROJECT_ARCHITECTURE.md](docs/PROJECT_ARCHITECTURE.md).

Bản mẫu chỉ lập đường cho đa giác lồi, không tránh vật cản hoặc bám địa hình.
Chỉ dùng SITL để phát triển/kiểm thử; chưa xác minh cho UAV thật.

## Chạy không Docker

Cài Gazebo Harmonic và các thư viện Qt hệ thống trên host. PX4 có script setup:

```bash
bash cmd/setup_px4.sh
```

Tạo môi trường Python (Conda là tùy chọn):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python src/main.py
```

Khởi động một PX4/Gazebo ở terminal riêng bằng lệnh SITL ở trên, thay `/app`
bằng đường dẫn repository trên host. `environment_basic.yml` là lựa chọn Conda.

## Phạm vi bản mẫu

Giữ GUI mẫu, bản đồ, zigzag mẫu, CSV mission, bảng kết quả, dự đoán hồi quy
năng lượng/thời gian và service MAVSDK một UAV.
Bỏ GUI cũ nhiều tab, điều phối swarm, AI/video, gimbal/rescue, MATLAB,
các script nghiên cứu/huấn luyện năng lượng và bộ thuật toán tối ưu cũ. Nhánh này thay đổi API GUI cũ.
Model/log/test local được ignore và không đưa vào repository. Ứng dụng không
cần model AI để khởi động; model hồi quy là tùy chọn để hiện dự đoán.
