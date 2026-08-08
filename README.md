# Hệ thống Giám sát Hành vi Đa Camera & Cảnh báo Phân vùng Thời gian thực

Dự án này là một hệ thống AI giám sát an ninh thời gian thực, sử dụng **YOLOv8** và **ByteTrack** để phát hiện và theo dõi người. Điểm đặc biệt của hệ thống là khả năng chụp trực tiếp từ các cửa sổ ứng dụng camera trên PC (như Imou Life) thông qua **Windows Graphics Capture API**, loại bỏ nhu cầu kết nối RTSP phức tạp[cite: 3, 5].

##  Tính năng nổi bật

*   **Chụp hình qua Cửa sổ (Window Capture):** Tự động bám theo cửa sổ ứng dụng camera (kiểu OBS), chống lặp màn hình (Feedback loop).
*   **Phân vùng Cảnh báo (Zone A/B/C):** 
    *   Hỗ trợ vẽ tự do các vùng giám sát trực tiếp trên video.
    *   Thang báo động 3 mức độ (Mức 0: Bình thường, Mức 1: Vàng, Mức 2: Đỏ chớp nháy)[cite: 4].
*   **Face Re-ID:** Nhận diện khuôn mặt để nối lại ID tự động khi bị đứt track (do khựng FPS hoặc bị che khuất).
*   **Bộ lọc Vật thể tĩnh:** Tự động loại bỏ các đồ vật bị AI nhận nhầm thành người nếu chúng không di chuyển trong một khoảng thời gian[cite: 8].
*   **Điều khiển Luồng Đôi (Dual Console):** CMD1 chuyên nhận thông báo khẩn cấp (cần xác nhận `Y/N`), CMD2 chuyên dùng để gán vùng, xác minh và đặt biệt danh[cite: 3, 6, 7].

## 💻 Yêu cầu hệ thống

*   **OS:** Windows 10/11 (Được khuyến nghị để sử dụng tối đa tính năng Window Capture).
*   **Python:** Môi trường phát triển Python 3.12.
*   **Phần cứng:** Hệ thống hoạt động tốt trên các cấu hình desktop tiêu chuẩn (ví dụ: các bản dựng sử dụng mainboard chipset H310 trở lên) nhưng yêu cầu bắt buộc phải có **GPU rời** (Khuyến nghị NVIDIA RTX 3060 12GB trở lên) để đảm bảo tốc độ 30-60 FPS cho toàn bộ Canvas[cite: 1, 3].

##  Cài đặt

1. **Clone kho lưu trữ:**
   ```bash
   git clone [https://github.com/your-username/your-repo-name.git](https://github.com/your-username/your-repo-name.git)
   cd your-repo-name
