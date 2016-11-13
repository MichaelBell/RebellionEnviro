#!/usr/bin/env python

import time
import cherrypy
from envirophat import weather, analog

class WeatherServer:
  def __init__(self):
    self.data = {}
    self.history_data = []
    self.last_history = time.time()

  @cherrypy.expose
  @cherrypy.tools.json_out()
  def status(self):
    cherrypy.response.headers["Access-Control-Allow-Origin"] = "http://sternpi:8080"
    return self.data

  def read_data(self):
    t = time.time()
    self.data = {
      'Time': int(t),
      'PiTemp': round(weather.temperature(), 2),
      'Temp': round((analog.read(0) - 0.5)*100.0, 2),
      'Pres': round(weather.pressure() / 100.0, 2) }
    if t > self.last_history + 29.0:
      self.history_data.append(self.data)
      self.last_history += 30.0

  @cherrypy.expose
  @cherrypy.tools.json_out()
  def history(self, readings="300", interval="1"):
    cherrypy.response.headers["Access-Control-Allow-Origin"] = "http://sternpi:8080"
    readings, interval = int(readings), int(interval)
    start = -readings*interval
    if -start > len(self.history_data):
      start = len(self.history_data)
      start = start - (start % interval)
      start = -start
    data = []
    for i in xrange(start, -interval, interval):
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
  print "Rebellion Weather Server"
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
