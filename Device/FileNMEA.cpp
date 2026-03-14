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

#include <cstring>
#include <ctime>
#include <sstream>

#include "FileNMEA.h"

namespace Device
{

	std::time_t NMEAFile::parseTimestamp(const std::string& ts)
	{
		if (ts.length() < 14) return 0;

		std::tm tm = {};
		tm.tm_year = std::stoi(ts.substr(0, 4)) - 1900;
		tm.tm_mon = std::stoi(ts.substr(4, 2)) - 1;
		tm.tm_mday = std::stoi(ts.substr(6, 2));
		tm.tm_hour = std::stoi(ts.substr(8, 2));
		tm.tm_min = std::stoi(ts.substr(10, 2));
		tm.tm_sec = std::stoi(ts.substr(12, 2));

		return std::mktime(&tm);
	}

	bool NMEAFile::parseLine(const std::string& line, NMEALine& parsed)
	{
		parsed.signalpower = LEVEL_UNDEFINED;
		parsed.ppm = PPM_UNDEFINED;
		parsed.timestamp = 0;

		// Find NMEA sentence (starts with ! or $)
		size_t start = line.find_first_of("!$");
		if (start == std::string::npos) return false;

		// Find metadata section (starts with " (")
		size_t meta_start = line.find(" (", start);
		if (meta_start != std::string::npos)
		{
			parsed.nmea = line.substr(start, meta_start - start);

			std::string meta = line.substr(meta_start);

			// Extract timestamp: YYYYMMDDHHMMSS
			size_t ts_pos = meta.find("timestamp:");
			if (ts_pos != std::string::npos)
			{
				size_t ts_start = ts_pos + 11;
				while (ts_start < meta.length() && meta[ts_start] == ' ') ts_start++;
				std::string ts;
				while (ts_start < meta.length() && std::isdigit(meta[ts_start]))
				{
					ts += meta[ts_start++];
				}
				if (ts.length() >= 14)
					parsed.timestamp = parseTimestamp(ts);
			}

			// Extract signalpower
			size_t sp_pos = meta.find("signalpower:");
			if (sp_pos != std::string::npos)
			{
				size_t sp_start = sp_pos + 12;
				while (sp_start < meta.length() && meta[sp_start] == ' ') sp_start++;
				try
				{
					parsed.signalpower = std::stof(meta.substr(sp_start));
				}
				catch (...) {}
			}

			// Extract ppm
			size_t ppm_pos = meta.find("ppm:");
			if (ppm_pos != std::string::npos)
			{
				size_t ppm_start = ppm_pos + 4;
				while (ppm_start < meta.length() && meta[ppm_start] == ' ') ppm_start++;
				try
				{
					parsed.ppm = std::stof(meta.substr(ppm_start));
				}
				catch (...) {}
			}
		}
		else
		{
			// No metadata, just NMEA sentence (trim trailing whitespace)
			parsed.nmea = line.substr(start);
			size_t end = parsed.nmea.find_last_not_of(" \t\r\n");
			if (end != std::string::npos)
				parsed.nmea = parsed.nmea.substr(0, end + 1);
		}

		return !parsed.nmea.empty();
	}

	void NMEAFile::Run()
	{
		NMEALine current;
		std::time_t baseline = 0;
		std::chrono::steady_clock::time_point wall_start;

		try
		{
			while (Device::isStreaming() && !file.eof())
			{
				std::string line;
				if (!std::getline(file, line)) break;

				if (!parseLine(line, current)) continue;

				if (realtime && speed > 0 && current.timestamp > 0)
				{
					if (baseline == 0)
					{
						baseline = current.timestamp;
						wall_start = std::chrono::steady_clock::now();
					}
					else
					{
						// Calculate when this message should be sent
						double delay_seconds = (double)(current.timestamp - baseline) / speed;
						auto target_time = wall_start + std::chrono::milliseconds((long)(delay_seconds * 1000));

						// Wait until target time
						auto now = std::chrono::steady_clock::now();
						if (target_time > now)
						{
							std::this_thread::sleep_until(target_time);
						}
					}
				}

				// Update tag with metadata if available
				if (current.signalpower != LEVEL_UNDEFINED)
					tag.level = current.signalpower;
				if (current.ppm != PPM_UNDEFINED)
					tag.ppm = current.ppm;

				// Send the NMEA sentence
				RAW r = {Format::TXT, (void*)current.nmea.c_str(), (int)current.nmea.length()};
				Send(&r, 1, tag);
			}

			if (loop && Device::isStreaming())
			{
				file.clear();
				file.seekg(0);
				Run();
			}
			else
			{
				done = true;
			}
		}
		catch (std::exception& e)
		{
			Error() << "NMEAFile Run: " << e.what();
			done = true;
		}
	}

	void NMEAFile::Play()
	{
		Device::Play();

		file.open(filename, std::ios::in);
		if (!file.is_open())
			throw std::runtime_error("NMEAFILE: Cannot open input file: " + filename);

		done = false;
		run_thread = std::thread(&NMEAFile::Run, this);
	}

	void NMEAFile::Stop()
	{
		if (Device::isStreaming())
		{
			Device::Stop();

			if (run_thread.joinable())
				run_thread.join();
		}
	}

	void NMEAFile::Close()
	{
		if (file.is_open())
		{
			file.close();
		}
	}

	Setting& NMEAFile::Set(std::string option, std::string arg)
	{
		Util::Convert::toUpper(option);

		if (option == "FILE")
		{
			filename = arg;
		}
		else if (option == "LOOP")
		{
			loop = Util::Parse::Switch(arg);
		}
		else if (option == "SPEED")
		{
			speed = Util::Parse::Float(arg, 0.0f, 100.0f);
		}
		else if (option == "REALTIME")
		{
			realtime = Util::Parse::Switch(arg);
		}
		else
		{
			throw std::runtime_error("Invalid NMEAFile setting: \"" + option + "\"");
		}

		return *this;
	}

	std::string NMEAFile::Get()
	{
		return "file " + filename + " speed " + std::to_string(speed) + " realtime " + Util::Convert::toString(realtime) + " loop " + Util::Convert::toString(loop);
	}
}
