/**
 * Admin password modal — placeholder for sensitive operations (P2-05 stub).
 *
 * Real sha256 verification is deferred (see PROJECT.md §10). For now the modal
 * merely collects a password and passes it via `onConfirm(password)` — caller
 * is responsible for sending it as the `X-Admin-Password` header on the actual
 * privileged request.
 */
import { useState } from "react";
import { Input, Modal, Typography } from "antd";

const { Text } = Typography;

interface Props {
  open: boolean;
  title?: string;
  onConfirm: (password: string) => void;
  onCancel: () => void;
}

export default function AdminPasswordModal({ open, title, onConfirm, onCancel }: Props) {
  const [password, setPassword] = useState("");

  const handleOk = () => {
    onConfirm(password);
    setPassword("");
  };

  const handleCancel = () => {
    setPassword("");
    onCancel();
  };

  return (
    <Modal
      open={open}
      title={title || "管理员密码"}
      okText="确认"
      cancelText="取消"
      onOk={handleOk}
      onCancel={handleCancel}
      okButtonProps={{ disabled: !password }}
    >
      <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
        敏感操作需要管理员密码。v1 stub 尚未做真实校验。
      </Text>
      <Input.Password
        placeholder="输入管理员密码"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoFocus
      />
    </Modal>
  );
}
