import paramiko

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)

# Check OOM killer
stdin, stdout, stderr = ssh.exec_command('sudo dmesg | grep -i "killed process\|out of memory" | tail -5')
print("OOM check:", stdout.read().decode().strip() or "None")

# Check available RAM
stdin, stdout, stderr = ssh.exec_command('free -m')
print("\nRAM:\n" + stdout.read().decode())

# Check stderr from last run
stdin, stdout, stderr = ssh.exec_command(
    'cd /home/ubuntu/scraper && source venv/bin/activate && '
    'python -c "import pandas; print(pandas.__version__); import openpyxl; print(openpyxl.__version__)"'
)
print("Imports:", stdout.read().decode().strip())
err = stderr.read().decode().strip()
if err: print("Import error:", err[:500])

ssh.close()
