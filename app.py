# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.2
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# +
import streamlit as st
import csv
from typing import List, Dict
import os
import ast
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from datetime import datetime

def find_csv_file(filename: str) -> str:
    """Search for the CSV file in the current directory and its parent."""
    current_dir = os.getcwd()
    possible_paths = [
        os.path.join(current_dir, filename),
        os.path.join(current_dir, 'Data', filename),
        os.path.join(os.path.dirname(current_dir), filename),
        os.path.join(os.path.dirname(current_dir), 'Data', filename)
    ]
    for path in possible_paths:
        if os.path.isfile(path):
            return path
    return None

def read_csv_data(file_path: str) -> List[Dict]:
    if not file_path:
        st.error(f"Error: Unable to find the CSV file.")
        return []
    try:
        with open(file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            data = [row for row in reader]
            return data
    except FileNotFoundError:
        st.error(f"Error: The file '{file_path}' was not found.")
        return []
    except Exception as e:
        st.error(f"Error reading the CSV file: {str(e)}")
        return []

def calculate_repair_cost_and_severity(damaged_parts: List[str], csv_data: List[Dict]) -> tuple:
    for row in csv_data:
        if 'Dented_part' in row:
            try:
                row_parts = ast.literal_eval(row['Dented_part'])
                if set(damaged_parts) == set(row_parts):
                    return float(row.get('Estimated_repair_cost', 0)), row.get('severity', 'Unknown')
            except (ValueError, SyntaxError):
                continue
    return 0, "Unknown"

def get_garage_details(location: str, garage_data: List[Dict], booking_data: List[Dict]) -> tuple:
    available_garages = [garage for garage in garage_data if garage.get('Location', '').lower() == location.lower()]
    if not available_garages:
        return f"No garages found in {location}.", [], []
    result = f"Available garages in {location}:\n"
    for garage in available_garages:
        result += f"Name: {garage.get('Garage_name', 'Unknown')}, "
        result += f"Rating: {garage.get('Rating', 'N/A')}, "
        result += f"Review: {garage.get('Review', 'No review available')}\n"
        garage_bookings = [booking for booking in booking_data if booking.get('Garage_name', '') == garage.get('Garage_name', '')]
        if garage_bookings:
            result += "Available time slots:\n"
            for booking in garage_bookings:
                result += f"Time: {booking.get('Time_slots_available', 'N/A')}, Status: {booking.get('status', 'Unknown')}\n"
        else:
            result += "No available time slots found for this garage.\n"
        result += "\n"
    return result, available_garages, booking_data

def book_appointment(available_garages: List[Dict], booking_data: List[Dict], chosen_garage: str, chosen_time: str) -> str:
    selected_garage = next((garage for garage in available_garages if garage.get('Garage_name', '').lower() == chosen_garage.lower()), None)
    if selected_garage:
        garage_bookings = [booking for booking in booking_data if booking.get('Garage_name', '') == selected_garage.get('Garage_name', '')]
        if garage_bookings:
            available_booking = next((booking for booking in garage_bookings if booking.get('status', '').lower() == 'available'), None)
            if available_booking:
                time_slot = available_booking.get('Time_slots_available', '')
                try:
                    chosen_datetime = datetime.strptime(chosen_time, "%I:%M %p")
                    start_time, end_time = map(lambda x: datetime.strptime(x.strip(), "%I:%M %p"), time_slot.split('to'))
                    if start_time <= chosen_datetime <= end_time:
                        return f"Successfully booked appointment at {selected_garage.get('Garage_name', '')} for {chosen_time}."
                    else:
                        return "The chosen time is outside the available slot. Please try again."
                except ValueError:
                    return "Invalid time format. Please use the format 'HH:MM AM/PM'."
            else:
                return "No available time slots for this garage. Please choose another."
        else:
            return "No booking information available for this garage. Please choose another."
    else:
        return "Invalid garage name. Please try again."

def generate_text_and_cost(project_id: str, image_path: str) -> tuple:
    try:
        vertexai.init(project=project_id, location="us-central1")
        model = GenerativeModel(model_name="gemini-1.5-flash-001")
        parts = [
            Part.from_uri(image_path, mime_type="image/jpeg"),
            "Analyze the following image of a car and identify any damaged parts. Respond with a Python list of the damaged parts, like ['hood', 'headlamp', 'front_bumper']. Only include the list in your response, with no additional text."
        ]
        response = model.generate_content(parts)
        damaged_parts = ast.literal_eval(response.text)
        csv_file_path = find_csv_file('car-damage-data.csv')
        csv_data = read_csv_data(csv_file_path)
        if not csv_data:
            return "Unable to proceed due to missing car damage data.", [], "Unknown", 0
        estimated_cost, severity = calculate_repair_cost_and_severity(damaged_parts, csv_data)
        result = f"Damaged parts: {damaged_parts}\nSeverity: {severity}\nEstimated repair cost: ${estimated_cost:.2f}"
        return result, damaged_parts, severity, estimated_cost
    except Exception as e:
        return f"An error occurred: {str(e)}", [], "Unknown", 0

def main():
    st.title("Car Damage Analysis and Appointment Booking")

    project_id = "gcp-hackathon-playzone"  # Replace with your actual project ID
    
    image_path = st.text_input("Enter the GCS path to your image (e.g., gs://your-bucket/your-image.jpg):")
    
    if st.button("Analyze Damage"):
        if image_path:
            result, damaged_parts, severity, estimated_cost = generate_text_and_cost(project_id, image_path)
            st.write(result)
            
            if damaged_parts:
                schedule_appointment = st.radio("Would you like to schedule a garage appointment?", ("Yes", "No"))
                
                if schedule_appointment == "Yes":
                    garage_data_path = find_csv_file('Data/garage-details-Copy1.csv')
                    booking_data_path = find_csv_file('Data/garage-booking-details.csv')
                    
                    garage_data = read_csv_data(garage_data_path)
                    booking_data = read_csv_data(booking_data_path)
                    
                    if not garage_data or not booking_data:
                        st.error("Unable to schedule appointment due to missing garage or booking data.")
                    else:
                        locations = list(set(garage.get('Location', '') for garage in garage_data))
                        chosen_location = st.selectbox("Please specify which location you prefer:", locations)
                        
                        if st.button("Get Garage Details"):
                            garage_details, available_garages, booking_data = get_garage_details(chosen_location, garage_data, booking_data)
                            st.write(garage_details)
                            
                            chosen_garage = st.selectbox("Please select a garage:", [garage.get('Garage_name', '') for garage in available_garages])
                            chosen_time = st.text_input("Please enter a time (e.g., 4:00 PM):")
                            
                            if st.button("Book Appointment"):
                                booking_result = book_appointment(available_garages, booking_data, chosen_garage, chosen_time)
                                st.write(booking_result)
                elif schedule_appointment == "No":
                    st.write("Thank you for using our service.")
        else:
            st.error("Please enter a valid image path.")

if __name__ == "__main__":
    main()

# -


