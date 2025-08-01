#!/usr/bin/env python3
"""
Generate secure keys for EnableOps application
Creates SESSION_SECRET and ENCRYPTION_MASTER_KEY
"""

import secrets
import base64
import os

def generate_session_secret():
    """Generate a secure session secret"""
    # Generate 32 bytes of random data
    return secrets.token_urlsafe(32)

def generate_encryption_master_key():
    """Generate a secure encryption master key"""
    # Generate 32 bytes of random data for AES-256
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

def main():
    print("🔐 EnableOps Security Key Generator")
    print("=" * 50)
    
    # Generate keys
    session_secret = generate_session_secret()
    encryption_key = generate_encryption_master_key()
    
    print("\n✅ Generated secure keys:")
    print(f"\nSESSION_SECRET={session_secret}")
    print(f"ENCRYPTION_MASTER_KEY={encryption_key}")
    
    print("\n📋 Copy these values to your .env file:")
    print("-" * 50)
    print(f"SESSION_SECRET={session_secret}")
    print(f"ENCRYPTION_MASTER_KEY={encryption_key}")
    print("-" * 50)
    
    # Ask if user wants to update .env file automatically
    update_env = input("\n🤔 Would you like to update your .env file automatically? (y/N): ").lower().strip()
    
    if update_env == 'y':
        try:
            # Read current .env file
            env_file = ".env"
            if os.path.exists(env_file):
                with open(env_file, 'r') as f:
                    content = f.read()
                
                # Update the keys
                lines = content.split('\n')
                updated_lines = []
                session_updated = False
                encryption_updated = False
                
                for line in lines:
                    if line.startswith('SESSION_SECRET='):
                        updated_lines.append(f'SESSION_SECRET={session_secret}')
                        session_updated = True
                    elif line.startswith('ENCRYPTION_MASTER_KEY='):
                        updated_lines.append(f'ENCRYPTION_MASTER_KEY={encryption_key}')
                        encryption_updated = True
                    else:
                        updated_lines.append(line)
                
                # Add keys if they weren't found
                if not session_updated:
                    updated_lines.append(f'SESSION_SECRET={session_secret}')
                if not encryption_updated:
                    updated_lines.append(f'ENCRYPTION_MASTER_KEY={encryption_key}')
                
                # Write back to file
                with open(env_file, 'w') as f:
                    f.write('\n'.join(updated_lines))
                
                print(f"✅ Updated {env_file} with new keys!")
            else:
                print("❌ .env file not found. Please create it first.")
        
        except Exception as e:
            print(f"❌ Error updating .env file: {e}")
            print("Please copy the keys manually.")
    
    print("\n🔒 Security Notes:")
    print("• Keep these keys secret and secure")
    print("• Never commit them to version control")
    print("• Use different keys for development and production")
    print("• Store production keys in secure environment variables")
    
    print("\n🚀 Next steps:")
    print("1. Update your .env file with the generated keys")
    print("2. Run: python setup_enableops.py")
    print("3. Start your application!")

if __name__ == "__main__":
    main()