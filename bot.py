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

# API های صرافی با درصد تغییرات واقعی
BINANCE_24HR_API = 'https://api.binance.com/api/v3/ticker/24hr?symbol=TONUSDT'
OKX_API = 'https://www.okx.com/api/v5/market/ticker?instId=TON-USDT'
GATE_API = 'https://api.gateio.ws/api/v4/spot/tickers?currency_pair=TON_USDT'


class TonPriceBot:
    def __init__(self, token, channel):
        self.bot = Bot(token=token)
        self.channel = channel
        self.session = None
        self.last_sent_price = None  # آخرین قیمتی که ارسال شده
        self.last_sent_change = None  # آخرین درصد تغییری که ارسال شده
        self.is_first_message = True  # آیا پیام اول است؟

    async def get_ton_price_from_exchange(self):
        """دریافت قیمت و درصد تغییرات مستقیم از صرافی"""
        
        for attempt in range(3):
            try:
                if not self.session:
                    self.session = aiohttp.ClientSession()
                
                # اولویت 1: Binance 24hr Ticker (درصد تغییرات 24 ساعته واقعی)
                try:
                    async with self.session.get(BINANCE_24HR_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            current_price = Decimal(str(data['lastPrice']))
                            # درصد تغییرات 24 ساعته از صرافی
                            change_percent = Decimal(str(data['priceChangePercent']))
                            
                            logger.info(f"✅ Binance: قیمت=${current_price} | تغییرات 24h={change_percent:.2f}% (از صرافی)")
                            return current_price, change_percent
                except Exception as e:
                    logger.warning(f"Binance 24hr خطا: {e}")
                
                # اولویت 2: OKX Ticker (درصد تغییرات از صرافی)
                try:
                    async with self.session.get(OKX_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('code') == '0' and 'data' in data:
                                ticker = data['data'][0]
                                current_price = Decimal(str(ticker['last']))
                                # درصد تغییرات UTC0 (24 ساعته)
                                change_percent_str = ticker.get('sodUtc0', '0')
                                change_percent = Decimal(str(change_percent_str)) * 100  # تبدیل به درصد
                                
                                logger.info(f"✅ OKX: قیمت=${current_price} | تغییرات 24h={change_percent:.2f}% (از صرافی)")
                                return current_price, change_percent
                except Exception as e:
                    logger.warning(f"OKX خطا: {e}")
                
                # اولویت 3: Gate.io (درصد تغییرات از صرافی)
                try:
                    async with self.session.get(GATE_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            if isinstance(data, list) and len(data) > 0:
                                ticker = data[0]
                                current_price = Decimal(str(ticker['last']))
                                # درصد تغییرات به صورت رشته مثل "+2.34%"
                                change_str = ticker.get('change_percentage', '0%').replace('%', '').replace('+', '')
                                change_percent = Decimal(str(change_str))
                                
                                logger.info(f"✅ Gate.io: قیمت=${current_price} | تغییرات 24h={change_percent:.2f}% (از صرافی)")
                                return current_price, change_percent
                except Exception as e:
                    logger.warning(f"Gate.io خطا: {e}")
                
                if attempt < 2:
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"خطا در تلاش {attempt + 1}: {e}")
        
        logger.error("❌ نتوانستیم از هیچ صرافی قیمت دریافت کنیم")
        return None, None

    async def format_message(self, price, change_percent):
        """فرمت پیام - نمایش دقیقاً 3 رقم اعشار با درصد تغییرات و فلش"""
        # قیمت با 3 رقم اعشار
        price_rounded = price.quantize(Decimal('0.001'), rounding=ROUND_DOWN)
        price_str = f"${price_rounded:.3f}"
        
        # تعیین فلش بر اساس مثبت یا منفی بودن
        if change_percent > 0:
            symbol = "▲"
            change_str = f"[+{change_percent:.2f}%]"
        elif change_percent < 0:
            symbol = "▼"
            change_str = f"[{change_percent:.2f}%]"
        else:
            # برای صفر (ارسال نمی‌شود)
            symbol = "▬"
            change_str = f"[{change_percent:.2f}%]"
        
        # فرمت نهایی: $1.578 ▲ [+3.44%]
        message = f"<b>{price_str} {symbol} {change_str}</b>"
        return message

    async def send_price_update(self):
        """ارسال قیمت به کانال - با درصد تغییرات واقعی از صرافی"""
        try:
            price, change_percent = await self.get_ton_price_from_exchange()
            
            if price is None or change_percent is None:
                logger.error("❌ نتوانستیم قیمت یا درصد تغییرات دریافت کنیم")
                return False
            
            # 🚫 جلوگیری از ارسال پیام با تغییر صفر (⚪)
            if change_percent == 0:
                logger.info(f"⏭️ تغییر صفر است، ارسال نمی‌شود: ${price} [0.00%]")
                return False
            
            # 🚫 جلوگیری از ارسال تکراری
            if self.last_sent_price is not None and self.last_sent_change is not None:
                # اگر هم قیمت و هم درصد عینا تکراری باشند
                price_diff = abs(price - self.last_sent_price)
                change_diff = abs(change_percent - self.last_sent_change)
                
                # اگر تفاوت خیلی کم باشد (کمتر از 0.001 دلار و 0.01 درصد)
                if price_diff < Decimal('0.001') and change_diff < Decimal('0.01'):
                    logger.info(f"⏭️ قیمت تکراری است، ارسال نمی‌شود: ${price} [{change_percent:.2f}%]")
                    return False
            
            # ✅ ارسال پیام
            message = await self.format_message(price, change_percent)
            
            await self.bot.send_message(
                chat_id=self.channel,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
            # ذخیره قیمت و درصد ارسال شده
            self.last_sent_price = price
            self.last_sent_change = change_percent
            self.is_first_message = False
            
            current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            logger.info(f"✅ پیام ارسال شد: {message} - {current_time}")
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
