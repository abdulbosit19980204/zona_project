// Foydali frontend uchun pm2 konfiguratsiyasi (foydali-setup.sh /etc/foydali/ ga nusxalaydi, __SRC__ ni almashtiradi).
// Port 3020 — 3000 ni bio-lab.uz frontendi (biolab-frontend) ishlatadi.
module.exports = {
  apps: [
    {
      name: "foydali-frontend",
      cwd: "__SRC__/frontend",
      script: "node_modules/next/dist/bin/next",
      args: "start -p 3020 -H 127.0.0.1",
      env: {
        NODE_ENV: "production",
        BACKEND_URL: "http://127.0.0.1:8020",
        QRDRIVE_URL: "http://127.0.0.1:8120",
      },
      max_memory_restart: "1G",
      autorestart: true,
      restart_delay: 3000,
      out_file: "/var/log/foydali-frontend.out.log",
      error_file: "/var/log/foydali-frontend.err.log",
      merge_logs: true,
      time: true,
    },
  ],
};
