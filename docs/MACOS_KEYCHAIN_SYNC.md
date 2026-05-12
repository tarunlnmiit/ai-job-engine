# macOS Keychain .env Sync

These commands allow you to securely store your `.env` variables in your macOS Keychain and retrieve them when needed. This is useful for keeping sensitive keys out of plain-text files when not in use.

## 1. Export `.env` to Apple Passwords (Keychain)
Run this command to save all variables from your current `.env` file into your macOS Keychain. They will be stored with a service name prefixed by the current directory name.

```bash
cat .env | grep -v '^#' | grep -v '^$' | while IFS='=' read -r key value; do \
  security add-generic-password -s "$(basename $(pwd))-$key" -a "$(basename $(pwd))" -w "$value" -U 2>/dev/null || \
  security set-generic-password-value -s "$(basename $(pwd))-$key" -w "$value"; \
done && echo "✅ Imported to Apple Passwords"
```

## 2. Restore `.env` from Apple Passwords (Keychain)
Run this command to recreate your `.env` file using the values stored in your macOS Keychain. It uses `.env.example` as a template for the keys.

```bash
cat .env.example | grep -v '^#' | grep -v '^$' | while IFS='=' read -r key _; do \
  echo "$key=$(security find-generic-password -w -s "$(basename $(pwd))-$key" 2>/dev/null)"; \
done > .env && echo "✅ Created .env from Apple Passwords"
```

---
> [!IMPORTANT]
> * **Service Name**: The variables are stored using the folder name as a prefix (`folder-KEY`). If you rename the folder, you will need to re-import or update the commands.
> * **Security**: While more secure than a plain-text file, anyone with access to your unlocked Mac and terminal can still run these commands to retrieve the values.
