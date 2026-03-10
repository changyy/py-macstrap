# macstrap config examples

This folder contains ready-to-use config directories for `macstrap run --config`.

Available example configs:
- `ai-cli`
- `openclaw`
- `utilities-dev`
- `php8.3-dev`

Examples:

```bash
macstrap run --config examples/ai-cli 192.168.1.101 --tag nvm --tag npm
macstrap run --config examples/php8.3-dev 192.168.1.101 --tag macports
macstrap run --dir examples/ai-cli --dir examples/openclaw --dir examples/utilities-dev 192.168.1.101
```
