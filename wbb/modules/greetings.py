"""
MIT License

Copyright (c) 2021 TheHamkerCat

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import asyncio
import os
from wbb import app, WELCOME_DELAY_KICK_SEC, SUDOERS
from wbb.modules.admin import member_permissions
from wbb.core.decorators.errors import capture_err
from wbb.utils.filter_groups import welcome_captcha_group
from wbb.utils.functions import generate_captcha
from wbb.utils.dbfunctions import (
    is_gbanned_user, is_captcha_on, captcha_on, captcha_off,
    set_welcome, del_welcome, get_welcome
)
from pykeyboard import InlineKeyboard
from pyrogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, ChatPermissions, User
)
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant, ChatAdminRequired
from pyrogram import filters
from random import shuffle
from datetime import datetime

__MODULE__ = "Greetings"
__HELP__ = """
/captcha [ON|OFF] - Enable/Disable captcha.

/set_welcome - Reply this to a message containing correct
format for a welcome message, check end of this message.

/del_welcome - Delete the welcome message.
/get_welcome - Get the welcome message.

**SET_WELCOME ->**

The format should be something like below.

```
**Hi** {name} Welcome to {chat}

~ #This separater (~) should be there between text and buttons, remove this comment also

button=[Duck, https://duckduckgo.com]
button2=[Github, https://github.com]
```

**NOTES ->**

for /rules, you can do /filter rules to a message
containing rules of your groups whenever a user
sends /rules, he'll get the message
"""


answers_dicc = []


@app.on_message(filters.new_chat_members, group=welcome_captcha_group)
@capture_err
async def welcome(_, message: Message):
    global answers_dicc
    """Mute new member and send message with button"""
    if not await is_captcha_on(message.chat.id):
        return
    for member in message.new_chat_members:
        try:
            if member.id in SUDOERS:
                continue  # ignore sudos
            if await is_gbanned_user(member.id):
                await message.chat.kick_member(member.id)
                await message.reply_text(f"{member.mention} was globally banned, and got removed,"
                                         + " if you think this is a false gban, you can appeal"
                                         + " for this ban in support chat.")
                continue
            if member.is_bot:
                continue  # ignore bots
            await message.chat.restrict_member(member.id, ChatPermissions())
            text = (f"{(member.mention())} Are you human?\n"
                    f"Solve this captcha in {WELCOME_DELAY_KICK_SEC} seconds and 4 attempts or you'll be kicked.")
        except ChatAdminRequired:
            return
        # Generate a captcha image, answers and some wrong answers
        captcha = generate_captcha()
        captcha_image = captcha[0]
        captcha_answer = captcha[1]
        wrong_answers = captcha[2]  # This consists of 8 wrong answers
        correct_button = InlineKeyboardButton(
            f"{captcha_answer}",
            callback_data=f"pressed_button {captcha_answer} {member.id}"
        )
        temp_keyboard_1 = [correct_button]  # Button row 1
        temp_keyboard_2 = []  # Botton row 2
        temp_keyboard_3 = []
        for i in range(2):
            temp_keyboard_1.append(
                InlineKeyboardButton(
                    f"{wrong_answers[i]}",
                    callback_data=f"pressed_button {wrong_answers[i]} {member.id}"
                )
            )
        for i in range(2, 5):
            temp_keyboard_2.append(
                InlineKeyboardButton(
                    f"{wrong_answers[i]}",
                    callback_data=f"pressed_button {wrong_answers[i]} {member.id}"
                )
            )
        for i in range(5, 8):
            temp_keyboard_3.append(
                InlineKeyboardButton(
                    f"{wrong_answers[i]}",
                    callback_data=f"pressed_button {wrong_answers[i]} {member.id}"
                )
            )

        shuffle(temp_keyboard_1)
        keyboard = [temp_keyboard_1, temp_keyboard_2, temp_keyboard_3]
        shuffle(keyboard)
        verification_data = {
            "user_id": member.id,
            "answer": captcha_answer,
            "keyboard": keyboard,
            "attempts": 0
        }
        keyboard = InlineKeyboardMarkup(keyboard)
        # Append user info, correct answer and
        answers_dicc.append(verification_data)
        # keyboard for later use with callback query
        button_message = await message.reply_photo(
            photo=captcha_image,
            caption=text,
            reply_markup=keyboard,
            quote=True
        )
        os.remove(captcha_image)
        asyncio.create_task(kick_restricted_after_delay(
            WELCOME_DELAY_KICK_SEC, button_message, member))
        await asyncio.sleep(0.5)


async def send_welcome_message(callback_query, pending_user_id):
    try:
        raw_text = await get_welcome(callback_query.message.chat.id)
    except TypeError:
        return
    raw_text = raw_text.strip().replace("`", "")
    if not raw_text:
        return
    text = raw_text.split("~")[0].strip()
    buttons_text_list = raw_text.split("~")[1].strip().splitlines()
    if "{chat}" in text:
        text = text.replace("{chat}", callback_query.message.chat.title)
    if "{name}" in text:
        text = text.replace("{name}", (await app.get_users(pending_user_id)).mention)
    buttons = InlineKeyboard(row_width=2)
    list_of_buttons = []
    for button_string in buttons_text_list:
        button_string = button_string.strip().split("=")[1].strip()
        button_string = button_string.replace("[", "").strip()
        button_string = button_string.replace("]", "").strip()
        button_string = button_string.split(",")
        button_text = button_string[0].strip()
        button_url = button_string[1].strip()
        list_of_buttons.append(
            InlineKeyboardButton(
                text=button_text,
                url=button_url
            )
        )
    buttons.add(*list_of_buttons)
    await app.send_message(
        callback_query.message.chat.id,
        text=text,
        reply_markup=buttons,
        disable_web_page_preview=True
    )


@app.on_callback_query(filters.regex("pressed_button"))
async def callback_query_welcome_button(_, callback_query):
    """After the new member presses the correct button,
    set his permissions to chat permissions,
    delete button message and join message.
    """
    global answers_dicc
    data = callback_query.data
    pending_user = await app.get_users(int(data.split(None, 2)[2]))
    pressed_user_id = callback_query.from_user.id
    pending_user_id = pending_user.id
    button_message = callback_query.message
    answer = data.split(None, 2)[1]
    if len(answers_dicc) != 0:
        for i in answers_dicc:
            if i['user_id'] == pending_user_id:
                correct_answer = i['answer']
                keyboard = i['keyboard']
    if pending_user_id == pressed_user_id:
        if answer != correct_answer:
            await callback_query.answer("Yeah, It's Wrong.")
            for iii in answers_dicc:
                if iii['user_id'] == pending_user_id:
                    attempts = iii['attempts']
                    if attempts >= 3:
                        answers_dicc.remove(iii)
                        await button_message.chat.kick_member(pending_user_id)
                        await asyncio.sleep(1)
                        await button_message.chat.unban_member(pending_user_id)
                        await button_message.delete()
                        return
                    else:
                        iii['attempts'] += 1
                        break
            shuffle(keyboard[0])
            shuffle(keyboard[1])
            shuffle(keyboard[2])
            shuffle(keyboard)
            keyboard = InlineKeyboardMarkup(keyboard)
            await button_message.edit(
                text=button_message.caption.markdown,
                reply_markup=keyboard
            )
            return
        await callback_query.answer("Captcha passed successfully!")
        await button_message.chat.unban_member(pending_user_id)
        await button_message.delete()
        if len(answers_dicc) != 0:
            for ii in answers_dicc:
                if ii['user_id'] == pending_user_id:
                    answers_dicc.remove(ii)

        """ send welcome message """
        await send_welcome_message(callback_query, pending_user_id)
        return
    else:
        await callback_query.answer("This is not for you")
        return


async def kick_restricted_after_delay(delay, button_message: Message, user: User):
    """If the new member is still restricted after the delay, delete
    button message and join message and then kick him
    """
    global answers_dicc
    await asyncio.sleep(delay)
    join_message = button_message.reply_to_message
    group_chat = button_message.chat
    user_id = user.id
    await join_message.delete()
    await button_message.delete()
    if len(answers_dicc) != 0:
        for i in answers_dicc:
            if i['user_id'] == user_id:
                answers_dicc.remove(i)
    await _ban_restricted_user_until_date(group_chat, user_id, duration=delay)


async def _ban_restricted_user_until_date(group_chat,
                                          user_id: int,
                                          duration: int):
    try:
        member = await group_chat.get_member(user_id)
        if member.status == "restricted":
            until_date = int(datetime.utcnow().timestamp() + duration)
            await group_chat.kick_member(user_id, until_date=until_date)
    except UserNotParticipant:
        pass


@app.on_message(filters.command("captcha") & ~filters.private)
@capture_err
async def captcha_state(_, message):
    usage = "**Usage:**\n/captcha [ON|OFF]"
    if len(message.command) != 2:
        await message.reply_text(usage)
        return
    user_id = message.from_user.id
    chat_id = message.chat.id
    permissions = await member_permissions(chat_id, user_id)
    if "can_restrict_members" not in permissions:
        await message.reply_text("You don't have enough permissions.")
        return
    state = message.text.split(None, 1)[1].strip()
    state = state.lower()
    if state == "on":
        await captcha_on(chat_id)
        await message.reply_text("Enabled Captcha For New Users.")
    elif state == "off":
        await captcha_off(chat_id)
        await message.reply_text("Disabled Captcha For New Users.")
    else:
        await message.reply_text(usage)


""" WELCOME MESSAGE """


@app.on_message(filters.command("set_welcome") & ~filters.private)
@capture_err
async def set_welcome_func(_, message):
    usage = "You need to reply to a text, check the Greetings module in /help"
    if not message.reply_to_message:
        await message.reply_text(usage)
        return
    if not message.reply_to_message.text:
        await message.reply_text(usage)
        return
    user_id = message.from_user.id
    chat_id = message.chat.id
    permissions = await member_permissions(chat_id, user_id)
    if "can_change_info" not in permissions:
        await message.reply_text("You don't have enough permissions.")
        return
    raw_text = str(message.reply_to_message.text.markdown)
    await set_welcome(chat_id, raw_text)
    await message.reply_text("Welcome message has been successfully set.")


@app.on_message(filters.command("del_welcome") & ~filters.private)
@capture_err
async def del_welcome_func(_, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    permissions = await member_permissions(chat_id, user_id)
    if "can_change_info" not in permissions:
        await message.reply_text("You don't have enough permissions.")
        return
    await del_welcome(chat_id)
    await message.reply_text("Welcome message has been deleted.")


@app.on_message(filters.command("get_welcome") & ~filters.private)
@capture_err
async def get_welcome_func(_, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    permissions = await member_permissions(chat_id, user_id)
    if "can_change_info" not in permissions:
        await message.reply_text("You don't have enough permissions.")
        return
    welcome_message = await get_welcome(chat_id)
    await message.reply_text(welcome_message)
