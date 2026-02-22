module.exports = {
  apps: [
    {
      name: "claude-coin-bot",
      script: "bot.py",
      interpreter: "/root/Claude Coin/.venv/bin/python",
      cwd: "/root/Claude Coin",
      env: { PYTHONUNBUFFERED: "1" },
      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 5000,
    },
  ],
};
