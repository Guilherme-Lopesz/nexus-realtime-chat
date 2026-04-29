 
import os
import base64
import hashlib
import json
import time
from datetime import datetime
from typing import Dict, Tuple, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import secrets
import hmac
import uuid

class CryptoSystem:
    """Sistema de criptografia completo para o Nexus Chat"""
    
    def __init__(self, master_key: Optional[str] = None):
        """Inicializa o sistema de criptografia"""
        self.master_key = master_key or os.getenv('MASTER_KEY')
        if not self.master_key:
            # Gerar uma chave mestra se não existir
            self.master_key = Fernet.generate_key().decode()
            os.environ['MASTER_KEY'] = self.master_key
            print("[CRIPTO] Chave mestra gerada e armazenada")
        
        # Dicionário para armazenar chaves de sessão por sala
        self.room_keys: Dict[str, bytes] = {}
        # Dicionário para armazenar chaves de usuário
        self.user_keys: Dict[str, Dict] = {}
        # Nonces para prevenção de replay attacks
        self.message_nonces: Dict[str, set] = {}
        
    def generate_user_keypair(self, username: str) -> Tuple[str, str]:
        """Gera um par de chaves RSA para um usuário"""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        public_key = private_key.public_key()
        
        # Serializar chaves
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Armazenar chaves
        self.user_keys[username] = {
            'private': private_pem,
            'public': public_pem,
            'created': datetime.utcnow().isoformat()
        }
        
        return public_pem.decode(), private_pem.decode()
    
    def derive_key_from_password(self, password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
        """Deriva uma chave de 32 bytes de uma senha usando PBKDF2"""
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        
        key = kdf.derive(password.encode())
        return key, salt
    
    def encrypt_aes_gcm(self, plaintext: str, key: bytes) -> Tuple[bytes, bytes, bytes]:
        """Criptografa texto usando AES-GCM (autenticado)"""
        # Gerar IV aleatório
        iv = os.urandom(12)
        
        # Criar cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv),
            backend=default_backend()
        )
        
        encryptor = cipher.encryptor()
        
        # Adicionar padding se necessário
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext.encode()) + padder.finalize()
        
        # Criptografar
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        return ciphertext, iv, encryptor.tag
    
    def decrypt_aes_gcm(self, ciphertext: bytes, key: bytes, iv: bytes, tag: bytes) -> str:
        """Descriptografa texto usando AES-GCM"""
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv, tag),
            backend=default_backend()
        )
        
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        # Remover padding
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
        
        return plaintext.decode()
    
    def encrypt_file(self, file_data: bytes, key: bytes) -> Tuple[bytes, bytes, bytes]:
        """Criptografa arquivos usando AES-CBC com padding"""
        # Gerar IV aleatório
        iv = os.urandom(16)
        
        # Criar cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        
        encryptor = cipher.encryptor()
        
        # Adicionar padding
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(file_data) + padder.finalize()
        
        # Criptografar
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        return ciphertext, iv
    
    def decrypt_file(self, ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
        """Descriptografa arquivos"""
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(ciphertext) + decryptor.finalize()
        
        # Remover padding
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_data) + unpadder.finalize()
        
        return plaintext
    
    def generate_hmac(self, data: bytes, key: bytes) -> str:
        """Gera HMAC para verificação de integridade"""
        h = hmac.new(key, data, hashlib.sha256)
        return h.hexdigest()
    
    def verify_hmac(self, data: bytes, key: bytes, received_hmac: str) -> bool:
        """Verifica HMAC para integridade"""
        expected_hmac = self.generate_hmac(data, key)
        return hmac.compare_digest(expected_hmac, received_hmac)
    
    def encrypt_message_for_room(self, message: str, room_id: str, sender: str) -> Dict:
        """Criptografa uma mensagem para uma sala específica"""
        if room_id not in self.room_keys:
            # Gerar chave para a sala se não existir
            self.room_keys[room_id] = os.urandom(32)
        
        room_key = self.room_keys[room_id]
        
        # Gerar nonce único para prevenir replay attacks
        nonce = str(uuid.uuid4())
        
        # Adicionar metadados à mensagem
        message_data = {
            'content': message,
            'sender': sender,
            'timestamp': datetime.utcnow().isoformat(),
            'nonce': nonce,
            'room': room_id
        }
        
        message_json = json.dumps(message_data, ensure_ascii=False)
        
        # Criptografar a mensagem
        ciphertext, iv, tag = self.encrypt_aes_gcm(message_json, room_key)
        
        # Gerar HMAC para integridade
        hmac_data = ciphertext + iv + tag
        message_hmac = self.generate_hmac(hmac_data, room_key)
        
        # Armazenar nonce para prevenção de replay
        if room_id not in self.message_nonces:
            self.message_nonces[room_id] = set()
        self.message_nonces[room_id].add(nonce)
        
        return {
            'ciphertext': base64.b64encode(ciphertext).decode(),
            'iv': base64.b64encode(iv).decode(),
            'tag': base64.b64encode(tag).decode(),
            'hmac': message_hmac,
            'nonce': nonce,
            'room_id': room_id
        }
    
    def decrypt_message_for_room(self, encrypted_data: Dict, room_id: str) -> Tuple[Dict, bool]:
        """Descriptografa uma mensagem de uma sala"""
        if room_id not in self.room_keys:
            return None, False
        
        room_key = self.room_keys[room_id]
        
        try:
            # Decodificar dados
            ciphertext = base64.b64decode(encrypted_data['ciphertext'])
            iv = base64.b64decode(encrypted_data['iv'])
            tag = base64.b64decode(encrypted_data['tag'])
            nonce = encrypted_data['nonce']
            received_hmac = encrypted_data['hmac']
            
            # Verificar HMAC
            hmac_data = ciphertext + iv + tag
            if not self.verify_hmac(hmac_data, room_key, received_hmac):
                return None, False
            
            # Verificar nonce para prevenir replay attacks
            if room_id in self.message_nonces and nonce in self.message_nonces[room_id]:
                return None, False  # Nonce já usado
            
            # Descriptografar
            message_json = self.decrypt_aes_gcm(ciphertext, room_key, iv, tag)
            message_data = json.loads(message_json)
            
            # Verificar se a mensagem é para a sala correta
            if message_data.get('room') != room_id:
                return None, False
            
            # Adicionar nonce à lista de usados
            if room_id not in self.message_nonces:
                self.message_nonces[room_id] = set()
            self.message_nonces[room_id].add(nonce)
            
            # Limitar tamanho da lista de nonces para evitar uso excessivo de memória
            if len(self.message_nonces[room_id]) > 10000:
                # Remover os mais antigos (manter últimos 10000)
                self.message_nonces[room_id] = set(list(self.message_nonces[room_id])[-10000:])
            
            return message_data, True
            
        except Exception as e:
            print(f"[CRIPTO] Erro ao descriptografar mensagem: {str(e)}")
            return None, False
    
    def encrypt_file_for_storage(self, file_data: bytes, room_id: str) -> Dict:
        """Criptografa um arquivo para armazenamento seguro"""
        if room_id not in self.room_keys:
            self.room_keys[room_id] = os.urandom(32)
        
        room_key = self.room_keys[room_id]
        
        # Criptografar arquivo
        ciphertext, iv = self.encrypt_file(file_data, room_key)
        
        # Gerar HMAC para integridade do arquivo
        file_hmac = self.generate_hmac(ciphertext + iv, room_key)
        
        return {
            'ciphertext': base64.b64encode(ciphertext).decode(),
            'iv': base64.b64encode(iv).decode(),
            'hmac': file_hmac,
            'room_id': room_id,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def decrypt_file_from_storage(self, encrypted_file: Dict, room_id: str) -> Optional[bytes]:
        """Descriptografa um arquivo armazenado"""
        if room_id not in self.room_keys:
            return None
        
        room_key = self.room_keys[room_id]
        
        try:
            ciphertext = base64.b64decode(encrypted_file['ciphertext'])
            iv = base64.b64decode(encrypted_file['iv'])
            received_hmac = encrypted_file['hmac']
            
            # Verificar integridade
            if not self.verify_hmac(ciphertext + iv, room_key, received_hmac):
                return None
            
            # Descriptografar
            file_data = self.decrypt_file(ciphertext, room_key, iv)
            
            return file_data
            
        except Exception as e:
            print(f"[CRIPTO] Erro ao descriptografar arquivo: {str(e)}")
            return None
    
    def encrypt_database_field(self, plaintext: str) -> Tuple[str, str]:
        """Criptografa campos do banco de dados"""
        # Usar chave mestra para criptografia do banco
        key = self.master_key.encode()[:32].ljust(32, b'0')[:32]
        
        ciphertext, iv, tag = self.encrypt_aes_gcm(plaintext, key)
        
        return base64.b64encode(ciphertext).decode(), base64.b64encode(iv + tag).decode()
    
    def decrypt_database_field(self, ciphertext: str, iv_tag: str) -> Optional[str]:
        """Descriptografa campos do banco de dados"""
        try:
            key = self.master_key.encode()[:32].ljust(32, b'0')[:32]
            ciphertext_bytes = base64.b64decode(ciphertext)
            iv_tag_bytes = base64.b64decode(iv_tag)
            
            iv = iv_tag_bytes[:12]
            tag = iv_tag_bytes[12:]
            
            plaintext = self.decrypt_aes_gcm(ciphertext_bytes, key, iv, tag)
            return plaintext
            
        except Exception as e:
            print(f"[CRIPTO] Erro ao descriptografar campo do banco: {str(e)}")
            return None
    
    def generate_session_key(self) -> str:
        """Gera uma chave de sessão para comunicação WebSocket"""
        return Fernet.generate_key().decode()
    
    def setup_room_encryption(self, room_id: str, password: Optional[str] = None) -> str:
        """Configura criptografia para uma sala"""
        if room_id in self.room_keys:
            return "Sala já possui criptografia configurada"
        
        if password:
            # Deriva chave da senha
            key, salt = self.derive_key_from_password(password)
            self.room_keys[room_id] = key
            return base64.b64encode(salt).decode()
        else:
            # Gera chave aleatória
            self.room_keys[room_id] = os.urandom(32)
            return "Chave aleatória gerada"
    
    def get_room_key_status(self, room_id: str) -> Dict:
        """Retorna status da criptografia da sala"""
        return {
            'encrypted': room_id in self.room_keys,
            'has_key': room_id in self.room_keys and self.room_keys[room_id] is not None
        }


# Instância global do sistema de criptografia
crypto_system = CryptoSystem()