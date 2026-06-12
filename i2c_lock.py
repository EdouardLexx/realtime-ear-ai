"""
i2c_lock.py
-----------
Verrou global partagé pour éviter les conflits I2C
entre le MAX30102 et l'ADS1115.
"""
import threading

i2c_lock = threading.Lock()
