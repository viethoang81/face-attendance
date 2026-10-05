# Hệ thống điểm danh sinh viên qua khuôn mặt tích hợp chống giả mạo

## 1. Giới thiệu

Đây là hệ thống điểm danh sinh viên bằng nhận diện khuôn mặt, được xây dựng dưới dạng ứng dụng desktop.

Hệ thống kết hợp nhận diện khuôn mặt với cơ chế kiểm tra chống giả mạo (anti-spoofing) nhằm hạn chế việc sử dụng hình ảnh hoặc phương tiện giả để thực hiện điểm danh.

Ngoài chức năng điểm danh, hệ thống hỗ trợ quản lý thông tin sinh viên, lớp học, môn học, ca học và dữ liệu điểm danh.

## 2. Chức năng chính

- Quản lý thông tin sinh viên.
- Quản lý lớp học.
- Quản lý môn học.
- Quản lý ca học.
- Đăng ký dữ liệu khuôn mặt cho sinh viên.
- Nhận diện khuôn mặt từ camera.
- Kiểm tra chống giả mạo trước khi xác nhận điểm danh.
- Thực hiện điểm danh theo ca học.
- Lưu kết quả điểm danh vào cơ sở dữ liệu.
- Tra cứu và xem dữ liệu điểm danh.

## 3. Công nghệ sử dụng

### Ứng dụng

- Python
- PyQt5
- OpenCV
- SQLite

### Nhận diện khuôn mặt

Hệ thống sử dụng thư viện `face_recognition` với phương pháp phát hiện khuôn mặt HOG.

Trong quá trình phát hiện, `face_recognition` sử dụng bộ phát hiện khuôn mặt của dlib.

### Chống giả mạo

Hệ thống tích hợp mô hình CNN anti-spoofing được huấn luyện riêng và triển khai dưới dạng ONNX.

Các thành phần của mô hình được lưu trong:

```text
assets/antispoof/
