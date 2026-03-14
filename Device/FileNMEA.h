/*
	Copyright(c) 2021-2025 jvde.github@gmail.com

	This program is free software: you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.

	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
	along with this program.  If not, see <https://www.gnu.org/licenses/>.
*/

#pragma once

#include "Device.h"

#include <fstream>
#include <chrono>

namespace Device {

	class NMEAFile : public Device {
		std::ifstream file;
		std::string filename;

		std::thread run_thread;

		bool done = false;
		bool loop = false;
		float speed = 1.0f;
		bool realtime = true;

		struct NMEALine {
			std::string nmea;
			std::time_t timestamp;
			float signalpower;
			float ppm;
		};

		bool parseLine(const std::string& line, NMEALine& parsed);
		std::time_t parseTimestamp(const std::string& ts);
		void Run();

	public:
		NMEAFile() : Device(Format::TXT, 0, Type::NMEAFILE) {}

		void Close();
		void Play();
		void Stop();

		bool isCallback() { return true; }
		bool isStreaming() { return Device::isStreaming() && !done; }

		Setting& Set(std::string option, std::string arg);
		std::string Get();

		std::string getProduct() { return "File (NMEA)"; }
		std::string getVendor() { return "File"; }
		std::string getSerial() { return filename; }
	};
}
