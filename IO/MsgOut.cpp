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
#include <vector>

#include "MsgOut.h"
#include "Receiver.h"
#include "DB.h"
#include "ETA.h"

namespace IO
{

	void OutputMessage::ConnectMessage(Receiver &r)
	{

		for (int j = 0; j < r.Count(); j++)
		{
			StreamIn<AIS::Message> *um = (StreamIn<AIS::Message> *)&*this;
			if (r.Output(j).canConnect(um->getGroupsIn()))
				r.Output(j).Connect(um);
		}
	}

	void OutputMessage::ConnectJSON(Receiver &r)
	{

		for (int j = 0; j < r.Count(); j++)
		{
			StreamIn<JSON::JSON> *um = (StreamIn<JSON::JSON> *)&*this;
			if (r.Output(j).canConnect(um->getGroupsIn()))
				r.OutputJSON(j).Connect(um);
		}
	}

	void OutputMessage::Connect(Receiver &r)
	{

		if (JSON_input)
			ConnectJSON(r);
		else
			ConnectMessage(r);

		for (int j = 0; j < r.Count(); j++)
		{

			StreamIn<AIS::GPS> *ug = (StreamIn<AIS::GPS> *)&*this;
			if (r.OutputGPS(j).canConnect(ug->getGroupsIn()))
				r.OutputGPS(j).Connect(ug);
		}
	}

	void OutputJSON::Connect(Receiver &r)
	{

		for (int j = 0; j < r.Count(); j++)
		{
			StreamIn<JSON::JSON> *um = (StreamIn<JSON::JSON> *)&*this;
			if (r.Output(j).canConnect(um->getGroupsIn()))
				r.OutputJSON(j).Connect(um);

			StreamIn<AIS::GPS> *ug = (StreamIn<AIS::GPS> *)&*this;
			if (r.OutputGPS(j).canConnect(ug->getGroupsIn()))
				r.OutputGPS(j).Connect(ug);
		}
	}

	void MessageToScreen::Receive(const AIS::GPS *data, int len, TAG &tag)
	{
		if (level == MessageFormat::SILENT)
			return;

		for (int i = 0; i < len; i++)
		{
			if (filter.includeGPS())
			{
				switch (level)
				{
				case MessageFormat::NMEA:
				case MessageFormat::NMEA_TAG:
				case MessageFormat::FULL:
					std::cout << data[i].getNMEA() << std::endl;
					break;
				default:
					std::cout << data[i].getJSON() << std::endl;
					break;
				}
			}
		}
	}

	void MessageToScreen::Receive(const Plane::ADSB *data, int len, TAG &tag)
	{
		for (int i = 0; i < len; i++)
		{
			//std::cout << "**** ADSB ****" << std::endl;
			//data[i].Print();
		}
	}

	void MessageToScreen::Receive(const AIS::Message *data, int len, TAG &tag)
	{

		if (level == MessageFormat::SILENT)
			return;

		for (int i = 0; i < len; i++)
		{
			if (filter.include(data[i]))
			{
				switch (level)
				{
				case MessageFormat::NMEA:
				case MessageFormat::NMEA_TAG:
					for (const auto &s : data[i].NMEA)
						std::cout << s << std::endl;
					break;
				case MessageFormat::FULL:
					for (const auto &s : data[i].NMEA)
					{
						
						std::cout << s << " ( ";

						if(data[i].getLength() > 0)							
							std::cout << "MSG: " << data[i].type() << ", REPEAT: " << data[i].repeat() << ", MMSI: " << data[i].mmsi();
						else
							std::cout << "empty";

						if (tag.mode & 1 && tag.ppm != PPM_UNDEFINED && tag.level != LEVEL_UNDEFINED)
							std::cout << ", signalpower: " << tag.level << ", ppm: " << tag.ppm;
						if (tag.mode & 2)
							std::cout << ", timestamp: " << data[i].getRxTime();
						if (data[i].getStation())
							std::cout << ", ID: " << data[i].getStation();

						std::cout << ")" << std::endl;
					}
					break;
				case MessageFormat::JSON_NMEA:
					std::cout << data[i].getNMEAJSON(tag.mode, tag.level, tag.ppm, tag.status, tag.hardware, tag.version, tag.driver, include_sample_start) << std::endl;
					break;
				default:
					break;
				}
			}
		}
	}

	void JSONtoScreen::Receive(const AIS::GPS *data, int len, TAG &tag)
	{
		for (int i = 0; i < len; i++)
		{
			if (filter.includeGPS())
			{
				std::cout << data[i].getJSON() << std::endl;
			}
		}
	}

	void JSONtoScreen::Receive(const JSON::JSON *data, int len, TAG &tag)
	{
		for (int i = 0; i < len; i++)
		{
			if (filter.include(*(AIS::Message *)data[i].binary))
			{
				json.clear();
				builder.stringify(data[i], json);
				std::cout << json << std::endl;
			}
		}
	}

	void ETAScreen::Start()
	{
		if (running) return;
		running = true;
		display_thread = std::thread(&ETAScreen::displayLoop, this);
	}

	void ETAScreen::Stop()
	{
		if (!running) return;
		running = false;
		if (display_thread.joinable())
			display_thread.join();
	}

	void ETAScreen::displayLoop()
	{
		while (running)
		{
			display();
			for (int i = 0; i < refresh_interval * 10 && running; i++)
			{
				SleepSystem(100);
			}
		}
	}

	void ETAScreen::display()
	{
		if (!db) return;

		std::vector<ETAInfo> approaching;

		{
			std::lock_guard<std::mutex> lock(db->mtx);

			const auto &ships = db->getShips();
			int idx = db->getFirst();

			while (idx != -1)
			{
				const Ship &ship = ships[idx];

				if (ship.lat != LAT_UNDEFINED && ship.lon != LON_UNDEFINED)
				{
					ETAInfo info = ETACalculator::calculate(ship, station_lat, station_lon);

					if (info.is_approaching && info.cpa_distance <= cpa_threshold && info.eta_minutes > 0)
					{
						approaching.push_back(info);
					}
				}

				idx = ship.next;
			}
		}

		// Sort by ETA (soonest first)
		std::sort(approaching.begin(), approaching.end(),
				  [](const ETAInfo &a, const ETAInfo &b)
				  { return a.eta_minutes < b.eta_minutes; });

		// Clear screen and display
		std::cout << "\033[2J\033[H";  // ANSI clear screen and move cursor to top

		std::cout << "============================================" << std::endl;
		std::cout << " APPROACHING SHIPS - ETA to Station" << std::endl;

		// Format station location
		char lat_dir = station_lat >= 0 ? 'N' : 'S';
		char lon_dir = station_lon >= 0 ? 'E' : 'W';
		std::cout << " Location: " << std::fixed << std::setprecision(4)
				  << std::abs(station_lat) << " " << lat_dir << ", "
				  << std::abs(station_lon) << " " << lon_dir << std::endl;

		// Current time
		std::time_t now = std::time(nullptr);
		std::tm *tm = std::localtime(&now);
		char time_buf[32];
		std::strftime(time_buf, sizeof(time_buf), "%H:%M:%S", tm);
		std::cout << " Updated: " << time_buf << " | CPA Threshold: "
				  << std::setprecision(1) << cpa_threshold << " NM" << std::endl;
		std::cout << "============================================" << std::endl;

		if (approaching.empty())
		{
			std::cout << std::endl;
			std::cout << "No ships approaching within " << cpa_threshold << " NM" << std::endl;
		}
		else
		{
			std::cout << std::left
					  << std::setw(21) << "NAME"
					  << std::setw(12) << "MMSI"
					  << std::setw(12) << "DIR"
					  << std::setw(8) << "ETA"
					  << std::setw(8) << "DIST" << std::endl;
			std::cout << "--------------------------------------------" << std::endl;

			for (const auto &info : approaching)
			{
				std::string name = info.name;
				if (name.empty() || name[0] == '\0')
					name = "Unknown";
				if (name.length() > 20)
					name = name.substr(0, 20);

				int eta_min = (int)info.eta_minutes;
				std::string eta_str;
				if (eta_min >= 60)
				{
					int hours = eta_min / 60;
					int mins = eta_min % 60;
					eta_str = std::to_string(hours) + "h" + std::to_string(mins) + "m";
				}
				else
				{
					eta_str = std::to_string(eta_min) + "min";
				}

				std::ostringstream dist_ss;
				dist_ss << std::fixed << std::setprecision(1) << info.current_distance << "nm";

				std::cout << std::left
						  << std::setw(21) << name
						  << std::setw(12) << info.mmsi
						  << std::setw(12) << info.direction
						  << std::setw(8) << eta_str
						  << std::setw(8) << dist_ss.str() << std::endl;
			}
			std::cout << "--------------------------------------------" << std::endl;
			std::cout << approaching.size() << " ship(s) approaching" << std::endl;
		}

		std::cout << std::endl;
	}

	Setting &ETAScreen::Set(std::string option, std::string arg)
	{
		Util::Convert::toUpper(option);

		if (option == "CPA")
		{
			cpa_threshold = Util::Parse::Float(arg, 0.1f, 100.0f);
		}
		else if (option == "REFRESH")
		{
			refresh_interval = Util::Parse::Integer(arg, 1, 3600);
		}
		else if (option == "LAT")
		{
			station_lat = Util::Parse::Float(arg, -90.0f, 90.0f);
		}
		else if (option == "LON")
		{
			station_lon = Util::Parse::Float(arg, -180.0f, 180.0f);
		}
		else
		{
			throw std::runtime_error("ETA output - unknown option: " + option);
		}

		return *this;
	}
}
