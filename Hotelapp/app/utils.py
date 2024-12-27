import hashlib
from datetime import datetime

from flask_login import current_user
from sqlalchemy import func, text

from app import db, dao, app, login
from app.models import User, CustomerType, Room, ReservationCustomer, RoomType, Customer, Reservation, \
    CustomerTypeRegulation, RoomRental, RoomTypeRegulation, RoomCustomerRegulation, SurchargeRegulation


def check_login(username, password):
    if username and password:
        password = str(hashlib.md5(password.strip().encode('utf-8')).hexdigest())

        return User.query.filter(User.username.__eq__(username.strip()),
                                 User.password.__eq__(password)).first()


def get_user_by_id(user_id):
    return User.query.get(user_id)


def get_customers_by_name(name=None):
    customers = (db.session.query(Customer.name, Customer.identification, User.avatar, CustomerType.type)
                 .outerjoin(User, User.id == Customer.id)) \
        .join(CustomerType, CustomerType.id.__eq__(Customer.customer_type_id))
    if name:
        customers = customers.filter(Customer.name.contains(name.strip()))
    return customers.all()



def calculate_total_reservation_price(reservation_info=None, room_id=None):
    if reservation_info and room_id:
        customers = reservation_info[room_id]['users']

        num_customers = len(customers)
        num_foreign_customers = 0
        for i in range(1, len(customers) + 1):
            if customers[i]['customerType'] == 'FOREIGN':
                num_foreign_customers += 1

        with app.app_context():
            room_price = db.session.query(Room.name, RoomType.name, RoomRegulation.price, RoomRegulation.surcharge,
                                          RoomRegulation.capacity, RoomRegulation.deposit_rate) \
                .join(Room, Room.room_type_id.__eq__(RoomType.id)) \
                .join(RoomRegulation, RoomRegulation.room_type_id.__eq__(RoomType.id)).filter(
                Room.id.__eq__(room_id)).first()

            total_price = room_price.price
            if num_customers == room_price.capacity:
                total_price += total_price * room_price.surcharge
            if num_foreign_customers > 0:
                customer_rate = db.session.query(CustomerType.type, CustomerTypeRegulation.rate) \
                    .join(CustomerTypeRegulation, CustomerTypeRegulation.customer_type_id.__eq__(CustomerType.id)) \
                    .filter(CustomerType.type.__eq__('FOREIGN')).first()
                total_price *= customer_rate.rate

            total_price *= room_price.deposit_rate

            reservation_info[room_id]['total_price'] = total_price
            return reservation_info


def check_reservation(checkin_time=datetime.now(), checkout_time=None, room_id=None, is_renting=False):
    if checkin_time and checkout_time:
        is_valid = True
        with ((app.app_context())):
            reservation = db.session.query(Reservation.checkin_date, Reservation.checkout_date)
            room_rental = db.session.query(RoomRental.checkin_date, RoomRental.checkout_date)

            if room_id:
                reservation = reservation.filter(Reservation.room_id.__eq__(room_id))
                room_rental = room_rental.filter(RoomRental.room_id.__eq__(room_id))

            for dt in reservation.all():
                if (dt[0] <= checkin_time <= dt[1]) or (dt[0] <= checkout_time <= dt[1]) or (
                        dt[0] >= checkin_time and dt[1] <= checkout_time):
                    is_valid = False
                    break
            if is_renting:
                for r in room_rental.all():
                    if (r[0] <= checkin_time <= r[1]) or (r[0] <= checkout_time <= r[1]) or (
                            r[0] >= checkin_time and r[1] <= checkout_time):
                        is_valid = False
                        break

        return is_valid


def check_customer_existence(customers=None):
    if customers:
        for cus in customers:
            customer = Customer.query.filter(
                Customer.identification.__eq__(customers[cus]['customerIdNum'])).first()
            if not customer or not customer.id:
                if cus == list(customers.keys())[-1]:
                    return False
            if customer and customer.id:
                return True

        return True


def get_cus_type_by_identification(identification=None):
    if identification:
        with app.app_context():
            cus_type = db.session.query(Customer.identification, Customer.name, Customer.customer_id, CustomerType.type) \
                .join(CustomerType, CustomerType.id.__eq__(Customer.customer_type_id)) \
                .filter(Customer.identification.__eq__(identification.strip())).first()
            if cus_type:
                return cus_type


def get_booked_rooms_by_identification(identification=None):
    if identification:
        with app.app_context():
            reservations = db.session.query(Reservation.id.label('reservation_id'), Reservation.deposit, Room.name,
                                            Reservation.checkin_date,
                                            Reservation.checkout_date) \
                .join(ReservationDetail, ReservationDetail.reservation_id.__eq__(Reservation.id)) \
                .join(Customer, Customer.customer_id.__eq__(ReservationDetail.customer_id)) \
                .join(Room, Room.id.__eq__(Reservation.room_id)) \
                .filter(Customer.identification.__eq__(identification.strip()),
                        Reservation.is_checkin.__eq__(False)).all()
            print(reservations)
            room_users = []
            for rs in reservations:
                r = db.session.query(ReservationDetail.reservation_id, Customer.name, Customer.identification) \
                    .join(ReservationDetail, ReservationDetail.customer_id.__eq__(Customer.customer_id)) \
                    .filter(ReservationDetail.reservation_id.__eq__(rs.reservation_id),
                            Reservation.id.__eq__(rs.reservation_id)).all()
                room_users.append(r)

            result = {}
            for rs in reservations:
                result[rs.reservation_id] = {
                    'reservation_id': rs.reservation_id,
                    'room': rs.name,
                    'checkin_date': rs.checkin_date,
                    'checkout_date': rs.checkout_date,
                    'room_users': [ru for ru in room_users if ru[0].reservation_id == rs.reservation_id],
                    'total_price': rs.deposit
                }

            return result


def get_rented_rooms_by_identification(identification=None):
    if identification:
        with app.app_context():
            customer = Customer.query.filter(Customer.identification.__eq__(identification.strip())).first()
            if customer:
                rented_rooms_from_reservation = db.session.query(ReservationDetail.customer_id,
                                                                 Reservation.id.label('reservation_id'),
                                                                 RoomRental.id.label('room_rental_id'),
                                                                 RoomRental.checkin_date,
                                                                 RoomRental.checkout_date,
                                                                 RoomRental.deposit.label('total_price'),
                                                                 Room.name.label('room_name'),
                                                                 Room.id.label('room_id')) \
                    .join(Reservation, Reservation.id.__eq__(ReservationDetail.reservation_id)) \
                    .join(RoomRental, RoomRental.reservation_id.__eq__(Reservation.id)) \
                    .join(Room, Room.id.__eq__(Reservation.room_id)) \
                    .filter(ReservationDetail.customer_id.__eq__(customer.customer_id),
                            Reservation.is_checkin.__eq__(True), RoomRental.is_paid.__eq__(False)).all()

                room_rentals = {}
                if rented_rooms_from_reservation:
                    for rr in rented_rooms_from_reservation:
                        r = db.session.query(Customer.name.label('name')) \
                            .join(ReservationDetail, ReservationDetail.customer_id.__eq__(Customer.customer_id)) \
                            .filter(ReservationDetail.reservation_id.__eq__(rr.reservation_id)).all()
                        room_rentals[rr.room_rental_id] = {
                            'room_id': rr.room_id,
                            'room_rental_id': rr.room_rental_id,
                            'room': rr.room_name,
                            'room_users': r,
                            'checkin_date': rr.checkin_date,
                            'checkout_date': rr.checkout_date,
                            'total_price': rr.total_price
                        }

                rented_rooms_by_direct_booking = db.session.query(Customer.customer_id,
                                                                  RoomRentalDetail.id,
                                                                  RoomRental.id.label('room_rental_id'),
                                                                  RoomRental.checkin_date,
                                                                  RoomRental.checkout_date,
                                                                  RoomRental.deposit.label('total_price'),
                                                                  Room.name.label('room_name'),
                                                                  Room.id.label('room_id')) \
                    .join(RoomRentalDetail, RoomRentalDetail.customer_id.__eq__(Customer.customer_id)) \
                    .join(RoomRental, RoomRental.id.__eq__(RoomRentalDetail.room_rental_id)) \
                    .join(Room, Room.id.__eq__(RoomRental.room_id)) \
                    .filter(Customer.identification.__eq__(identification.strip()),
                            RoomRental.is_paid.__eq__(False)).all()

                if rented_rooms_by_direct_booking:
                    for rr in rented_rooms_by_direct_booking:
                        r = db.session.query(Customer.name.label('name')) \
                            .join(RoomRentalDetail, RoomRentalDetail.customer_id.__eq__(Customer.customer_id)) \
                            .filter(RoomRentalDetail.room_rental_id.__eq__(rr.room_rental_id)).all()

                        room_rentals[rr.room_rental_id] = {
                            'room_id': rr.room_id,
                            'room_rental_id': rr.room_rental_id,
                            'room': rr.room_name,
                            'room_users': r,
                            'checkin_date': rr.checkin_date,
                            'checkout_date': rr.checkout_date,
                            'total_price': rr.total_price
                        }
                return room_rentals

# get_rented_rooms_by_identification(identification='192137035')
def stats_cart(cart):
    total_amount, total_quantity = 0, 0

    if cart:
        for c in cart.values():
            total_quantity += c['quantity']
            total_amount += c['quantity'] * c['price']

    return {
        "total_amount": total_amount,
        "total_quantity": total_quantity
    }