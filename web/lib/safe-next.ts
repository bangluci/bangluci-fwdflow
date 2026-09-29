/** Chỉ nhận đường dẫn nội bộ: bắt đầu bằng một dấu `/`, không phải `//` hay `/\` (trình duyệt coi là host khác). */
export function safeNext(next: string | null): string | null {
  return next && /^\/(?![/\\])/.test(next) ? next : null;
}
