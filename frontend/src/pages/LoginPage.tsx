/**
 * Login page — full-screen gradient stage with a glassmorphism sign-in card.
 *
 * User picks from the preconfigured usernames dropdown and clicks 登录.
 * No password validation in v1 for regular users; admin actions gate on
 * <AdminPasswordModal /> separately.
 */
import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Button, Form, Select } from "antd";
import { ArrowRightOutlined } from "@ant-design/icons";

import { listPreconfiguredUsers } from "@/api/auth";
import { useAuthStore } from "@/store/authStore";

export default function LoginPage() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState<string | undefined>(undefined);

  const users = listPreconfiguredUsers();
  const from = (location.state as { from?: string })?.from || "/";

  const onSubmit = () => {
    if (!username) return;
    login(username);
    navigate(from, { replace: true });
  };

  return (
    <div className="login-stage">
      <div className="orb orb-1" />
      <div className="orb orb-2" />

      <div className="login-card">
        <div className="login-logo">
          <span className="brand-logo-mark">📈</span>
          <div>
            <div className="login-title">istock</div>
            <div className="login-sub">A 股量化分析工具 · v0.1</div>
          </div>
        </div>

        <Form layout="vertical" onFinish={onSubmit}>
          <Form.Item label="选择登录用户" required>
            <Select
              size="large"
              placeholder="请选择一个用户"
              value={username}
              onChange={setUsername}
              options={users.map((u) => ({ value: u.username, label: u.label }))}
            />
          </Form.Item>
          <Button
            type="primary"
            size="large"
            htmlType="submit"
            block
            disabled={!username}
          >
            进入工作台 <ArrowRightOutlined />
          </Button>
        </Form>

        <span className="login-hint">
          v1 提示：常规用户无需密码，仅按 X-User 传递身份；管理员敏感操作走独立密码校验。
        </span>
      </div>
      <a
        className="login-icp-link"
        href="https://beian.miit.gov.cn/"
        target="_blank"
        rel="noreferrer"
      >
        蜀ICP备2026039813号
      </a>
    </div>
  );
}
