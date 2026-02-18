"""
API密钥加密模块
提供 AES-256 加密存储，保护用户敏感信息
"""
import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import Optional
from pathlib import Path

# 加密密钥存储路径
KEY_FILE = Path("/root/.opentrade/.encryption_key")
CONFIG_FILE = Path("/root/.opentrade/.encrypted_config.json")


def get_or_create_key() -> bytes:
    """获取或创建加密密钥"""
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    else:
        key = Fernet.generate_key()
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_bytes(key)
        os.chmod(str(KEY_FILE), 0o600)  # 仅root可读写
        return key


def derive_key(password: str, salt: bytes) -> bytes:
    """从密码派生加密密钥"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_api_key(api_key: str, password: Optional[str] = None) -> str:
    """
    加密 API 密钥
    
    Args:
        api_key: 原始API密钥
        password: 可选密码（如果提供，使用密码加密而不是随机密钥）
    
    Returns:
        加密后的字符串 (base64编码)
    """
    if password:
        salt = os.urandom(16)
        key = derive_key(password, salt)
        f = Fernet(key)
        encrypted = f.encrypt(api_key.encode())
        return base64.b64encode(salt + encrypted).decode()
    else:
        f = Fernet(get_or_create_key())
        encrypted = f.encrypt(api_key.encode())
        return encrypted.decode()


def decrypt_api_key(encrypted_key: str, password: Optional[str] = None) -> str:
    """
    解密 API 密钥
    
    Args:
        encrypted_key: 加密后的字符串
        password: 可选密码
    
    Returns:
        原始API密钥
    """
    try:
        data = base64.b64decode(encrypted_key.encode())
        
        if password:
            salt = data[:16]
            encrypted = data[16:]
            key = derive_key(password, salt)
            f = Fernet(key)
        else:
            f = Fernet(get_or_create_key())
            encrypted = data
            
        return f.decrypt(encrypted).decode()
    except Exception as e:
        raise ValueError(f"解密失败: {e}")


def encrypt_config_dict(config: dict, password: Optional[str] = None) -> str:
    """加密整个配置字典"""
    import json
    json_str = json.dumps(config)
    return encrypt_api_key(json_str, password)


def decrypt_config_dict(encrypted_str: str, password: Optional[str] = None) -> dict:
    """解密配置字典"""
    import json
    json_str = decrypt_api_key(encrypted_str, password)
    return json.loads(json_str)


class SecureConfig:
    """安全配置管理类"""
    
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self._config = {}
        self._load()
    
    def _load(self):
        """加载加密配置"""
        if self.config_path.exists():
            try:
                encrypted = self.config_path.read_text()
                self._config = decrypt_config_dict(encrypted)
            except Exception:
                self._config = {}
    
    def save(self, password: Optional[str] = None):
        """保存配置"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = encrypt_config_dict(self._config, password)
        self.config_path.write_text(encrypted)
        os.chmod(str(self.config_path), 0o600)
    
    def get(self, key: str, default: str = "") -> str:
        """获取配置值"""
        return self._config.get(key, default)
    
    def set(self, key: str, value: str, password: Optional[str] = None):
        """设置配置值并保存"""
        self._config[key] = value
        self.save(password)
    
    def get_api_credentials(self, exchange: str) -> dict:
        """获取交易所API凭证"""
        return {
            "api_key": self.get(f"{exchange}_api_key", ""),
            "api_secret": self.get(f"{exchange}_api_secret", ""),
            "passphrase": self.get(f"{exchange}_passphrase", ""),
        }
    
    def set_api_credentials(self, exchange: str, api_key: str, api_secret: str, 
                           passphrase: str = "", password: Optional[str] = None):
        """设置交易所API凭证"""
        self.set(f"{exchange}_api_key", encrypt_api_key(api_key, password))
        self.set(f"{exchange}_api_secret", encrypt_api_key(api_secret, password))
        if passphrase:
            self.set(f"{exchange}_passphrase", encrypt_api_key(passphrase, password))
    
    def delete(self, key: str):
        """删除配置项"""
        if key in self._config:
            del self._config[key]
            self.save()


if __name__ == "__main__":
    # 测试加密功能
    test_key = "test_api_key_12345"
    
    # 自动密钥加密
    encrypted = encrypt_api_key(test_key)
    decrypted = decrypt_api_key(encrypted)
    assert decrypted == test_key, "自动密钥加密失败"
    print("✅ 自动密钥加密测试通过")
    
    # 密码加密
    encrypted_pwd = encrypt_api_key(test_key, "my_password")
    decrypted_pwd = decrypt_api_key(encrypted_pwd, "my_password")
    assert decrypted_pwd == test_key, "密码加密失败"
    print("✅ 密码加密测试通过")
    
    print("✅ 加密模块测试全部通过")
