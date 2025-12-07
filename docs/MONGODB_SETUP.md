# MongoDB Remote Connection Setup

This guide explains how to configure MongoDB to accept remote connections for iCCC.

## Problem

By default, MongoDB only listens on `127.0.0.1` (localhost) and doesn't accept remote connections. You need to configure it to bind to all interfaces and enable authentication.

## Current Status

Based on diagnostic results:
- **TCP Connection**: ✗ Failed (Connection refused - Error 111)
- **Redis Connection**: ✓ Success
- **Likely Cause**: MongoDB not configured for remote access

## Solution

### On the MongoDB Server (192.168.123.104)

#### 1. Check MongoDB Status

```bash
sudo systemctl status mongod
```

If not running:
```bash
sudo systemctl start mongod
sudo systemctl enable mongod
```

#### 2. Configure MongoDB for Remote Access

Edit `/etc/mongod.conf`:

```bash
sudo nano /etc/mongod.conf
```

Update the network interfaces section:

```yaml
# Before (localhost only)
net:
  port: 27017
  bindIp: 127.0.0.1

# After (accept remote connections)
net:
  port: 27017
  bindIp: 0.0.0.0  # Listen on all interfaces
```

**Security Note**: Binding to `0.0.0.0` makes MongoDB accessible from any IP. For production:
```yaml
net:
  port: 27017
  bindIp: 127.0.0.1,192.168.123.104  # Localhost + specific IP
```

#### 3. Enable Authentication (Recommended)

In `/etc/mongod.conf`:

```yaml
security:
  authorization: enabled
```

#### 4. Restart MongoDB

```bash
sudo systemctl restart mongod
```

Verify it's listening on the correct interface:

```bash
sudo netstat -tlnp | grep 27017
# Should show: 0.0.0.0:27017 or 192.168.123.104:27017
```

#### 5. Configure Firewall

Allow MongoDB port through firewall:

**Ubuntu/Debian (ufw):**
```bash
sudo ufw allow from 192.168.123.0/24 to any port 27017
sudo ufw reload
```

**CentOS/RHEL (firewalld):**
```bash
sudo firewall-cmd --permanent --add-port=27017/tcp
sudo firewall-cmd --reload
```

**iptables:**
```bash
sudo iptables -A INPUT -p tcp --dport 27017 -s 192.168.123.0/24 -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

#### 6. Create Admin User (if not exists)

Connect to MongoDB locally:

```bash
mongosh
```

Create admin user:

```javascript
use admin

db.createUser({
  user: "admin",
  pwd: "your_admin_password",
  roles: [ { role: "userAdminAnyDatabase", db: "admin" } ]
})

exit
```

#### 7. Create Application User

Reconnect with admin credentials:

```bash
mongosh mongodb://admin:your_admin_password@localhost:27017/admin
```

Create `mongo` user for `iccc` database:

```javascript
use iccc

db.createUser({
  user: "mongo",
  pwd: "c790414J",
  roles: [
    { role: "readWrite", db: "iccc" },
    { role: "dbAdmin", db: "iccc" }
  ]
})

// Verify user was created
db.getUsers()

exit
```

#### 8. Test Connection Locally

```bash
mongosh "mongodb://mongo:c790414J@localhost:27017/iccc"
```

If successful, you should see:

```
Current Mongosh Log ID: ...
Connecting to: mongodb://localhost:27017/iccc
Using MongoDB: 6.0.x
```

### From the Client Machine

#### 1. Test TCP Connection

```bash
telnet 192.168.123.104 27017
# Or
nc -zv 192.168.123.104 27017
```

Should show: `Connection to 192.168.123.104 27017 port [tcp/*] succeeded!`

#### 2. Test MongoDB Connection

```bash
mongosh "mongodb://mongo:c790414J@192.168.123.104:27017/iccc"
```

#### 3. Run iCCC Connection Test

```bash
cd /opt/iflow/iccc
python scripts/test_connections.py
```

## Alternative: Use MongoDB Atlas (Cloud)

If you can't configure the server, use MongoDB Atlas:

1. **Create Free Cluster**: https://www.mongodb.com/cloud/atlas/register
2. **Get Connection String**: `mongodb+srv://username:password@cluster.mongodb.net/iccc`
3. **Update .env**:
   ```env
   MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net/iccc
   ```

## Development Alternative: Local MongoDB with SSH Tunnel

If you can SSH to the MongoDB server:

```bash
# Create SSH tunnel
ssh -L 27017:localhost:27017 user@192.168.123.104 -N

# In another terminal, update .env
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_USERNAME=mongo
MONGODB_PASSWORD=c790414J
MONGODB_DBNAME=iccc

# Run tests
python scripts/test_connections.py
```

## Testing Without MongoDB

For development without MongoDB access, use mongomock:

```bash
pip install mongomock-motor
```

Set environment variable:
```bash
export ICCC_USE_MOCK_DB=true
```

iCCC will use in-memory mocking for tests.

## Verification Checklist

On MongoDB Server:
- [ ] MongoDB is running (`systemctl status mongod`)
- [ ] Listening on 0.0.0.0:27017 (`netstat -tlnp | grep 27017`)
- [ ] Firewall allows port 27017 from client IP
- [ ] Authentication is enabled
- [ ] User `mongo` exists with correct password
- [ ] User `mongo` has permissions on `iccc` database

From Client:
- [ ] TCP connection succeeds (`telnet 192.168.123.104 27017`)
- [ ] MongoDB connection succeeds (`mongosh "mongodb://..."`)
- [ ] iCCC connection test passes (`python scripts/test_connections.py`)

## Troubleshooting

### Error: "Connection refused (111)"
- MongoDB not running or not bound to external IP
- Check `bindIp` in `/etc/mongod.conf`

### Error: "Authentication failed"
- Wrong username/password
- User doesn't exist or wrong authSource
- Try: `?authSource=admin` in connection string

### Error: "No route to host"
- Firewall blocking connection
- Check firewall rules on server

### Error: "Timeout"
- Network connectivity issue
- Wrong IP address
- MongoDB not listening on external interface

## Security Best Practices

1. **Use Strong Passwords**: Generate with `openssl rand -base64 32`
2. **Limit IP Access**: Use firewall rules to allow only specific IPs
3. **Use SSL/TLS**: Configure MongoDB with certificates for encrypted connections
4. **Regular Backups**: Use `mongodump` or MongoDB Atlas automated backups
5. **Monitor Access**: Enable MongoDB audit logging
6. **Network Segmentation**: Place MongoDB in private network, not public internet

## Next Steps

Once MongoDB is accessible:

1. Run connection tests: `python scripts/test_connections.py`
2. Initialize database: `python -m iccc.db.init_db`
3. Run integration tests: `pytest tests/integration/`
4. Start API server: `litestar run`
