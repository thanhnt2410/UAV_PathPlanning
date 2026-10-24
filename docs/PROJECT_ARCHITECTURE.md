# Basic: một UAV, một điểm thay thuật toán

Đây là bộ khung học tập/phát triển trong repo `UAV_PathPlanning`, được tách
từ nhánh `basic` của SW-UAV; GUI đầy đủ nằm ở repo SW-UAV gốc. Giữ Python/asyncio/MAVSDK và Qt; không dùng ROS làm kiến trúc.

```text
main.py → app.py → main_controller.py → interface_base.py + interface_map.py
                                    → services/mission_planner.py → planning/*
                                    → services/drone_service.py → MAVSDK → PX4
                                    → services/mission_io.py → CSV
```

- `main.py`: điểm vào chương trình, gọi `app.main()`.
- `app.py`: khởi động Qt và event loop qasync, không tự kết nối UAV.
- `main_controller.py`: nối signal/button với planner/service, lập đường qua worker thread.
- `utils/logger.py`: log ra console, không cần thư mục log có quyền ghi.
- `domain/mission.py`: waypoint GPS và altitude tương đối (m).
- `domain/uav.py`: snapshot telemetry, không phụ thuộc Qt.
- `planning/grid.py`: tạo các hàng khảo sát bên trong đa giác lồi, theo mét.
- `planning/path_algorithms.py`: `plan_path(points, start)` là điểm thay thuật toán.
  Đầu vào/đầu ra là `(latitude, longitude)`; đầu ra giữ đủ từng điểm khảo sát,
  không tự thêm depot. Không gửi lệnh bay ở đây.
- `services/mission_planner.py`: chuyển tọa độ, tạo lưới, gọi thuật toán,
  kiểm tra hoán vị và giới hạn, thêm `start` ở hai đầu. `compare()` chạy các
  hàm trong `get_algorithms()`, cô lập lỗi và trả `PlanningResult` cho mỗi hàm.
- `planning/uav_analyzer.py`: tính distance/turns/cost/coverage/overlap và đọc
  hai model hồi quy năng lượng/thời gian. Thiếu model trả dự đoán `None` kèm lý do,
  không làm mất kết quả hình học.
- `services/drone_service.py`: kết nối một UAV, cập nhật telemetry, upload,
  Arm/Disarm, Takeoff, Start/Resume, Pause, RTL và Land. Không tự arm.
- `services/mission_io.py`: CSV `latitude,longitude[,altitude]`, chuyển sang MAVSDK.
- `interface_base.py`: layout Qt mẫu và bảng kết quả; chọn dòng để đổi route.
  `main_controller.py` dùng route đang chọn cho Upload và kiểm tra route khi Start.
- `interface_map.py` và `assets/map.*`: bridge Qt/Leaflet. Click bản đồ để thêm
  đỉnh; có thể nhập/sửa tọa độ trực tiếp trong panel.
  Giữ nguyên các file map trong `assets`, gồm nguồn Google Hybrid ảnh vệ tinh.
  Adapter Python đăng ký `qtWidget`, gọi `drawPolygonJs`, `drawPolyLineJs` và API
  marker gốc. Polygon vẽ/sửa bằng Leaflet.Draw cập nhật vùng khảo sát trong GUI.
- `config/uav_config.yaml`: endpoint, thông số lập đường, analysis, energy_model
  và ngưỡng an toàn. Các dự đoán không thay thế battery/health checks khi bay.
- `config/init_pos_uavs.yaml`: giữ vị trí ban đầu của `uav_1` cho bản đồ và
  lập đường offline. Khi kết nối, planner dùng GPS thực; file không đặt vị trí SITL.
- `config/interface_config.yaml`: đường dẫn HTML của map gốc. Nguồn nền do
  `assets/map.js` quản lý; adapter không thay đổi nguồn ảnh hoặc code assets.
- `config/stream_config.yaml`: giữ file cấu hình stream để mở rộng; nội dung rỗng
  vì basic chưa có chức năng video. Giữ các file config, chỉ lược dữ liệu không dùng.

## Quy ước và giới hạn

Chỉ một kết nối MAVSDK; server đi kèm wheel `mavsdk` được SDK quản lý.
PX4/Gazebo là submodule ngoài, không được nhúng hoặc sửa bởi ứng dụng.
Không thay đổi các tham số flight controller/failsafe khi Connect.

Upload chỉ khi UAV disarmed và trên mặt đất. Arm là nút riêng; Takeoff và Start
đều kiểm tra connection, health, GPS, battery và flight mode với timeout.
Service giám sát telemetry khi bay, yêu cầu RTL nếu mất telemetry, GPS/health
không đạt, pin thấp hoặc mission quá thời hạn. Nếu link đã mất, RTL từ máy tính
có thể không gửi được; failsafe trên PX4 vẫn là lớp bảo vệ bắt buộc.
Pause/RTL/Land vẫn có thể gửi khi một thao tác GUI khác đang chạy.
Tiến độ mission được đọc bằng một stream riêng, chỉ cập nhật khi có sự kiện.
Không có cập nhật tiến độ không được coi là mất telemetry và không tự yêu cầu RTL;
vòng giám sát telemetry và thời hạn mission vẫn hoạt động độc lập.
Đóng app qua GUI yêu cầu UAV đã hạ cánh và disarm.

Đường mẫu là zigzag trên đa giác lồi ở phạm vi nhỏ (giới hạn radius trong config),
không có tránh vật cản, địa hình, vùng cấm hay kiểm chứng độ phủ của camera.
Mức cao là tương đối so với điểm cất cánh, không phải độ cao bám địa hình.
Đoạn nối depot nằm ngoài đa giác có thể đi ngoài vùng khảo sát.
Map gốc tải Leaflet/Leaflet.Draw từ CDN và ảnh vệ tinh Google, cần internet.
HTML/JavaScript map và QWebChannel được tải từ assets local.

Các API cũ cho nhiều UAV, Qt Designer UI cũ, rescue, gimbal, video/AI, các script
nghiên cứu/huấn luyện, bộ thuật toán tối ưu và export QGC đã được bỏ ở nhánh này.
Giữ đọc model hồi quy đã huấn luyện với features `total_distance_m`, `stop_count`.
`stop_count = len(mission) - 1`, bỏ depot đầu và tính waypoint quay về. Phần dự đoán
chạy trong worker cùng phần phân tích, không chặn Qt. `N/A` được giữ khi thiếu model
hoặc dự đoán không hợp lệ; không coi thiếu model là năng lượng 0. Dự đoán chưa tính
đúng mọi thay đổi vật lý của cấu hình basic, không phải đo năng lượng thực tế.
Người dùng GUI cũ cần dùng nhánh `main` của repo SW-UAV gốc; bản basic không tương thích API GUI cũ.

## Các file hỗ trợ bản basic

- `requirements.txt`, `environment_basic.yml`: dependency Qt/MAVSDK/geometry và pandas/scikit-learn cho hồi quy; bỏ AI/video.
- `docker/Dockerfile`, `docker/requirements.txt`, `docker/docker-compose.yml`,
  `docker/build.sh`: image basic và một container, không chọn CUDA/PyTorch.
  `docker/requirements-px4.txt` giữ dependency build PX4.
- `cmd/setup_px4.sh`: setup native và build PX4 gốc, không cài extension năng lượng.
- `.gitignore`, `.dockerignore`: giữ artifacts local khỏi Git và Docker build context.
- `assets/leaflet/*`: runtime Leaflet 1.9.4 kèm BSD license, thay cả cây node_modules.
- `README.md`: cài đặt một lần, chạy hằng ngày, extension points và giới hạn.

Các nhóm xóa: GUI Qt Designer/backup/samples cũ; controllers video và telemetry
phụ thuộc GUI cũ; mavsdk_server tự quản lý; utils cứu hộ/AI/video/map cũ;
geometry/optimizer/analysis dư thừa; assets cho UI/video cũ; tài liệu
nghiên cứu/UI cũ; scripts thu dữ liệu/huấn luyện; MATLAB; node_modules và
manifest npm; extension công suất Gazebo; `swam_uav.sh` điều phối nhiều UAV.
Các file model/log/test ignored có sẵn trên máy và checkout PX4 có thay đổi local
được giữ nguyên. Chỉ file ứng dụng được theo dõi trên Git mới được lọc bỏ.
