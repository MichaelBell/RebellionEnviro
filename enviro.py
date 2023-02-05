#!/usr/bin/env python3

import time
import cherrypy
import json
import ssl

from bme280 import BME280
from smbus import SMBus
import ST7735
from PIL import Image, ImageDraw, ImageFont
from fonts.ttf import RobotoMedium as UserFont

from secrets import MQTT_BROKER, MQTT_USERNAME, MQTT_PASSWORD
import paho.mqtt.client as mqtt

MQTT_PORT = 8883
MQTT_TOPIC = "enviroplus"

# mqtt callbacks
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT connected OK")
    else:
        print("MQTT not connected Returned code=", rc)


def on_publish(client, userdata, mid):
    print("MQTT mid: " + str(mid))

# Get Raspberry Pi serial number to use as ID
def get_serial_number():
    with open("/proc/cpuinfo", "r") as f:
        for line in f:
            if line[0:6] == "Serial":
                return line.split(":")[1].strip()

class WeatherServer:
  def __init__(self):
    self.data = {}
    self.history_data = []
    self.last_history = time.time()
    self.bus = SMBus(1)
    self.bme280 = BME280(i2c_dev=self.bus)

    self.display = ST7735.ST7735(
                port=0,
                cs=1,
                dc=9,
                backlight=12,
                rotation=90,
                spi_speed_hz=10000000
            )
    self.display.begin()
    self.img = Image.new('RGB', (self.display.width, self.display.height), color=(0, 0, 0))
    self.draw = ImageDraw.Draw(self.img)
    self.font = ImageFont.truetype(UserFont, 25)
    self.text_colour = (200, 200, 160)
    self.back_colour = (50, 0, 50)

    # Raspberry Pi ID
    device_serial_number = get_serial_number()
    self.device_id = "raspi-" + device_serial_number

    self.mqtt_client = mqtt.Client(client_id=self.device_id)
    self.mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    self.mqtt_client.on_connect = on_connect
    self.mqtt_client.on_publish = on_publish
    self.mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLSv1_2)
    self.mqtt_client.connect(MQTT_BROKER, port=MQTT_PORT)
    self.mqtt_client.loop_start()

  def update_display(self):
    self.draw.rectangle((0, 0, 160, 80), self.back_colour)
    text = "{:.1f}°C".format(self.data["Temp"])
    size_x, size_y = self.draw.textsize(text, self.font)
    x = (self.display.width / 3) - (size_x / 2)
    y = (self.display.height / 4) - (size_y / 2)
    self.draw.text((x, y), text, font=self.font, fill=self.text_colour)

    text = "{:.0f}%".format(self.data["Humid"])
    size_x, size_y = self.draw.textsize(text, self.font)
    x = (5 * self.display.width / 6) - (size_x / 2)
    y = (self.display.height / 4) - (size_y / 2)
    self.draw.text((x, y), text, font=self.font, fill=self.text_colour)

    text = "{:.1f}mB".format(self.data["Pres"])
    size_x, size_y = self.draw.textsize(text, self.font)
    x = (self.display.width - size_x) / 2
    y = (3 * self.display.height / 4) - (size_y / 2)
    self.draw.text((x, y), text, font=self.font, fill=self.text_colour)

    self.display.display(self.img)

  def origin_header(self):
    if "Origin" in cherrypy.request.headers:
      if cherrypy.request.headers["Origin"] in ("http://sternpi:8080", "http://battery.rebellionafloat.uk"):
        cherrypy.response.headers["Access-Control-Allow-Origin"] = cherrypy.request.headers["Origin"]

  @cherrypy.expose
  @cherrypy.tools.json_out()
  def status(self):
    self.origin_header()
    cherrypy.response.headers["Cache-Control"] = 'no-cache'
    return self.data

  def read_data(self):
    t = time.time()
    try:
      cur_data = {
        'Temperature' : round(self.bme280.get_temperature(), 2) - 6,
        'Pressure':     round(self.bme280.get_pressure(), 2),
        'Humidity':     round(self.bme280.get_humidity(), 1) }
      self.data = {
        'Time':  int(t),
        'Temp':  cur_data["Temperature"],
        'Pres':  cur_data["Pressure"],
        'Humid': cur_data["Humidity"] }
      if t > self.last_history + 29.0:
        self.history_data.append(self.data)
        self.last_history += 30.0
        self.mqtt_client.publish(MQTT_TOPIC, json.dumps(cur_data))
      self.update_display()
    except IOError:
      pass

  @cherrypy.expose
  @cherrypy.tools.json_out()
  def history(self, readings="300", interval="1"):
    self.origin_header()
    readings, interval = int(readings), int(interval)
    start = -readings*interval
    if -start > len(self.history_data):
      start = len(self.history_data)
      start = start - (start % interval)
      start = -start
    data = []
    for i in range(start, -interval, interval):
      data_slice = self.history_data[i:i+interval]
      data.append({
        "Time"   : data_slice[-1]["Time"],
        "Temp"   : sum([d['Temp'] for d in data_slice]) / interval,
        "Pres"   : sum([d['Pres'] for d in data_slice]) / interval
      })
    interval = interval if len(self.history_data) > interval else len(self.history_data)
    data_slice = self.history_data[-interval:]
    data.append({
      "Time"   : data_slice[-1]["Time"],
      "Temp"   : sum([d['Temp'] for d in data_slice]) / interval,
      "Pres"   : sum([d['Pres'] for d in data_slice]) / interval
    })
    return data


if __name__ == '__main__':
  print("Rebellion Weather Server")
  server = WeatherServer()
  cherrypy.tree.mount(server, '/')
  cherrypy.config.update({'engine.autoreload.on': False,
                          'server.socket_host'  : '0.0.0.0'})
  cherrypy.engine.start()
  
  try:
    while True:
      server.read_data()
      time.sleep(2)
  finally:
    cherrypy.engine.exit()
    server.display.set_backlight(0)
