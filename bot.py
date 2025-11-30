import os
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
import aiohttp

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# تنظیمات از محیط
BOT_TOKEN = os.getenv('BOT_TOKEN', '8326225213:AAGsScRkwKKGipb_z_57vfGeDBw6Iz-hkdA')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '@Ton24Price')

# API برای دریافت قیمت Toncoin با دقت بالا و درصد تغییرات
KUCOIN_API = 'https://api.kucoin.com/api/v1/market/stats?symbol=TON-USDT'
OKX_API = 'https://www.okx.com/api/v5/market/ticker?instId=TON-USDT'
BINANCE_API = 'https://api.binance.com/api/v3/ticker/24hr?symbol=TONUSDT'
COINGECKO_API = 'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd&include_24hr_change=true'


class TonPriceBot:
    def __init__(self, token, channel):
        self.bot = Bot(token=token)
        self.channel = channel
        self.session = None
        self.last_price = None
        self.last_change_percent = None
        self.last_message = None
        self.previous_price = None  # قیمت دقیقه قبل برای محاسبه تغییرات یک دقیقه‌ای

    async def get_ton_price_and_change(self):
        """دریافت قیمت Toncoin و درصد تغییرات 24 ساعته"""
        # تلاش 3 بار
        for attempt in range(3):
            try:
                if not self.session:
                    self.session = aiohttp.ClientSession()
                
                # اولویت 1: KuCoin (stats API برای دریافت changeRate)
                try:
                    async with self.session.get(KUCOIN_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('code') == '200000' and 'data' in data:
                                stats = data['data']
                                price = Decimal(str(stats['last']))
                                # changeRate در KuCoin یک عدد اعشاری است (مثلاً 0.0344 برای 3.44%)
                                change_rate = Decimal(str(stats.get('changeRate', '0'))) * 100
                                logger.info(f"✅ قیمت از KuCoin: ${price} | تغییرات: {change_rate}%")
                                self.last_price = price
                                self.last_change_percent = change_rate
                                return price, change_rate
                except Exception as e:
                    logger.warning(f"KuCoin خطا: {e}")
                
                # اولویت 2: OKX
                try:
                    async with self.session.get(OKX_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('code') == '0' and 'data' in data:
                                ticker = data['data'][0]
                                price = Decimal(str(ticker['last']))
                                # changeRate در OKX همان درصد است
                                change_rate = Decimal(str(ticker.get('changeRate', '0'))) * 100
                                logger.info(f"✅ قیمت از OKX: ${price} | تغییرات: {change_rate}%")
                                self.last_price = price
                                self.last_change_percent = change_rate
                                return price, change_rate
                except Exception as e:
                    logger.warning(f"OKX خطا: {e}")
                
                # اولویت 3: Binance (24hr ticker)
                try:
                    async with self.session.get(BINANCE_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            price = Decimal(str(data['lastPrice']))
                            change_rate = Decimal(str(data.get('priceChangePercent', '0')))
                            logger.info(f"✅ قیمت از Binance: ${price} | تغییرات: {change_rate}%")
                            self.last_price = price
                            self.last_change_percent = change_rate
                            return price, change_rate
                except Exception as e:
                    logger.warning(f"Binance خطا: {e}")
                
                # اولویت 4: CoinGecko
                try:
                    async with self.session.get(COINGECKO_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            ton_data = data['the-open-network']
                            price = Decimal(str(ton_data['usd']))
                            change_rate = Decimal(str(ton_data.get('usd_24h_change', '0')))
                            logger.info(f"✅ قیمت از CoinGecko: ${price} | تغییرات: {change_rate}%")
                            self.last_price = price
                            self.last_change_percent = change_rate
                            return price, change_rate
                except Exception as e:
                    logger.warning(f"CoinGecko خطا: {e}")
                
                if attempt < 2:
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"خطا در تلاش {attempt + 1}: {e}")
        
        # اگر همه تلاش‌ها ناموفق بود، از داده قبلی استفاده کن
        if self.last_price and self.last_change_percent is not None:
            logger.warning(f"⚠️ استفاده از داده قبلی: ${self.last_price} | {self.last_change_percent}%")
            return self.last_price, self.last_change_percent
        
        return None, None

    async def format_message(self, price, change_percent):
        """فرمت پیام - نمایش دقیقاً 3 رقم اعشار با درصد تغییرات و نماد"""
        # قیمت با 3 رقم اعشار
        price_rounded = price.quantize(Decimal('0.001'), rounding=ROUND_DOWN)
        price_str = f"${price_rounded:.3f}"
        
        # تعیین نماد بر اساس مثبت یا منفی بودن
        if change_percent > 0:
            symbol = "▲"
            change_str = f"[+{change_percent:.2f}%]"
        elif change_percent < 0:
            symbol = "▼"
            change_str = f"[{change_percent:.2f}%]"
        else:
            symbol = "●"
            change_str = f"[{change_percent:.2f}%]"
        
        # فرمت نهایی: $1.578 ▲ [+3.44%]
        message = f"<b>{price_str} {symbol} {change_str}</b>"
        return message

    async def send_price_update(self):
        """ارسال قیمت به کانال - با محاسبه تغییرات یک دقیقه‌ای"""
        try:
            price, _ = await self.get_ton_price_and_change()
            
            if price is None:
                logger.error("❌ نتوانستیم قیمت دریافت کنیم")
                return False
            
            # محاسبه درصد تغییرات یک دقیقه
            if self.previous_price is not None:
                # محاسبه تغییرات: ((قیمت فعلی - قیمت قبلی) / قیمت قبلی) * 100
                one_min_change = ((price - self.previous_price) / self.previous_price) * 100
            else:
                # اولین بار که ربات اجرا می‌شود
                one_min_change = Decimal('0')
            
            message = await self.format_message(price, one_min_change)
            
            # جلوگیری از ارسال پیام تکراری (اگر قیمت و درصد تغییر نکرده باشد)
            if message == self.last_message:
                logger.info(f"⏭️ پیام تکراری است، ارسال نمی‌شود: {message}")
                return False
            
            await self.bot.send_message(
                chat_id=self.channel,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
            # ذخیره پیام آخر برای مقایسه
            self.last_message = message
            
            # ذخیره قیمت فعلی به عنوان قیمت قبلی برای دقیقه بعد
            self.previous_price = price
            
            current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            logger.info(f"✅ قیمت ارسال شد: {message} - {current_time}")
            return True
            
        except TelegramError as e:
            logger.error(f"❌ خطای تلگرام: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ خطای غیرمنتظره: {e}")
            return False

    async def run(self):
        """اجرای ربات"""
        logger.info("🚀 ربات شروع شد")
        logger.info(f"📢 کانال: {self.channel}")
        
        try:
            bot_info = await self.bot.get_me()
            logger.info(f"✅ ربات متصل: @{bot_info.username}")
            
            while True:
                # صبر تا شروع دقیقه بعدی
                now = datetime.now(timezone.utc)
                seconds_to_wait = 60 - now.second
                logger.info(f"⏳ صبر {seconds_to_wait} ثانیه تا دقیقه بعدی...")
                await asyncio.sleep(seconds_to_wait)
                
                # ارسال قیمت
                await self.send_price_update()
                
        except KeyboardInterrupt:
            logger.info("⛔ ربات متوقف شد")
        except Exception as e:
            logger.error(f"❌ خطای کلی: {e}")
            await asyncio.sleep(60)
        finally:
            if self.session:
                await self.session.close()


async def main():
    """تابع اصلی"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN تنظیم نشده!")
        return
    
    bot = TonPriceBot(BOT_TOKEN, CHANNEL_USERNAME)
    await bot.run()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ برنامه متوقف شد")
