# A 股 VPS 收盘触发

VPS 在北京时间工作日 17:25 调用 `master` 的 `daily_t_close.yml`。请求使用
`mode=production`、`trigger_source=external-scheduler` 和明确的北京时间交易日期。
仅在 17:25 至 17:34 放行触发，工作流继续负责 XSHG 交易日校验、串行执行和已完成日期检查。

## 部署

将 `github_dispatch.py` 安装到 `/usr/local/lib/ashare-tclose-dispatch/`，将两个
systemd 单元安装到 `/etc/systemd/system/`。脚本依赖 Python 3.10+、系统时区数据和
`/usr/bin/openssl`。

使用仅安装到本仓库、具有 Actions 读写权限的 GitHub App。在
`/etc/ashare-tclose-dispatch/github-app.env` 设置 `ASHARE_GITHUB_APP_ID` 和
`ASHARE_GITHUB_INSTALLATION_ID`。将 PEM 存到
`/etc/ashare-tclose-dispatch/github-app.pem`，设属主 root、权限 0600。服务使用
systemd `LoadCredential` 读取私钥，按次申请仅限此仓库的安装令牌。

执行 `systemctl daemon-reload` 和 `systemd-analyze verify`，然后在 timer
尚未启用时运行下列非派发检查。

```sh
systemd-run --wait --pipe --collect \
  -p DynamicUser=yes \
  -p EnvironmentFile=/etc/ashare-tclose-dispatch/github-app.env \
  -p LoadCredential=github-app-key:/etc/ashare-tclose-dispatch/github-app.pem \
  /usr/bin/python3 /usr/local/lib/ashare-tclose-dispatch/github_dispatch.py --check
```

看到 `ASHARE_VPS_GITHUB_APP_AUTH_OK` 后，在经授权的切换窗口关闭
`ashare-tclose-dispatcher` 的 Cloudflare Cron，回读后执行
`systemctl enable --now ashare-tclose-dispatch.timer`。从
`journalctl -u ashare-tclose-dispatch.service` 取得首次运行链接，核对对应
Actions 运行的生产、已完成或节假日结果。回滚时先停用 VPS timer，再恢复 Cloudflare
的 `25 9 * * 1-5`。GitHub 原生 17:17 和 18:17 的定时继续提供原有入口。
