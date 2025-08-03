from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256
import base64
from binascii import hexlify, unhexlify

class cipher():
    def __init__(self):
        self.public_key_pem = self.read_key_pem("secret/public_key.pem")
        self.private_key_pem = self.read_key_pem("secret/private_key.pem")
        
    def generate_rsa_keys(key_size=2048):
        """
        Generates a new RSA public and private key pair.
        Key size should be at least 2048 for good security.
        """
        key = RSA.generate(key_size)
        private_key = key.export_key('PEM')
        public_key = key.publickey().export_key('PEM')
        return private_key, public_key

    def encrypt(self, message):
        """
        Encrypts a message using the RSA public key.
        The message must be bytes.
        """
        public_key = RSA.import_key(self.public_key_pem)
        cipher_rsa = PKCS1_OAEP.new(public_key, hashAlgo=SHA256)
        # PKCS1_OAEP is a padding scheme that adds randomness to the encryption,
        # making it more secure against certain attacks.
        encrypted_message = cipher_rsa.encrypt(message.encode('utf8'))
        return base64.b64encode(encrypted_message).decode('ascii')

    def decrypt(self, encrypted_message):
        """
        Decrypts an encrypted message using the RSA private key.
        """
        private_key = RSA.import_key(self.private_key_pem)
        cipher_rsa = PKCS1_OAEP.new(private_key, hashAlgo=SHA256)
        
        try:
            encode = encrypted_message.encode('ascii')
            decode = base64.b64decode(encode)
            decrypted_message = cipher_rsa.decrypt(decode)
        except Exception as e:
            raise(f"Decryption failed. {e}")

        return decrypted_message.decode("utf8")


    def read_key_pem(self,file_path):
        """
        Reads a key from a PEM file.
        Returns the key content as bytes.
        """
        try:
            with open(file_path, 'rb') as f: # Use 'rb' for read binary mode
                key_pem = f.read()
            return key_pem
        except FileNotFoundError:
            print(f"Error: Private key file not found at {file_path}")
            return None
        except Exception as e:
            print(f"An error occurred while reading the private key file: {e}")
            return None
        
if __name__ == "__main__":
    c = cipher()
    comm = input("what:")
    while comm != "q":
        if comm == "e":
            text = input("Enter the text:")
            t = c.encrypt(text)
            print("-------------------------------")
            print(t)
        elif comm == "d":
            text = input("Enter the text:")
            t = c.decrypt(text)
            print("-------------------------------")
            print(t)
        print("-------------------------------")
        comm = input()