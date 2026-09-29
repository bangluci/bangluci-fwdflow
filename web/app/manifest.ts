import type { MetadataRoute } from "next";

// Cho phép thêm app tài xế vào màn hình chính (PWA nhẹ, không làm offline đầy đủ).
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FwdFlow Tài xế",
    short_name: "FwdFlow",
    description: "Nhận việc, chụp ảnh bằng chứng và cập nhật trạng thái giao nhận",
    start_url: "/driver",
    scope: "/",
    display: "standalone",
    background_color: "#f4f7fa",
    theme_color: "#1c2c4a",
    lang: "vi",
    icons: [{ src: "/favicon.ico", sizes: "any", type: "image/x-icon" }],
  };
}
