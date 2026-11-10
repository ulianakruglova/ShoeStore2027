"""Модуль работы с БД PostgreSQL (версия 2027)."""

import psycopg2
from config import DB_CONFIG


class DatabaseManager:
    """Класс для управления подключением к БД."""

    def __init__(self):
        self.connection = None
        self.cursor = None

    def connect(self):
        try:
            self.connection = psycopg2.connect(**DB_CONFIG)
            self.cursor = self.connection.cursor()
            return True
        except Exception as error:
            print(f"Ошибка подключения к БД: {error}")
            return False

    def disconnect(self):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()


    # АВТОРИЗАЦИЯ (только по логину, без пароля)

    def authenticate_user(self, login):
        """Проверка логина пользователя (без пароля по ТЗ)."""
        query = """
            SELECT u.user_id, u.last_name, u.first_name, u.middle_name, r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.login = %s
        """
        self.cursor.execute(query, (login,))
        user = self.cursor.fetchone()

        if user:
            user_id = user[0]
            full_name = f"{user[1]} {user[2]} {user[3] or ''}".strip()
            role = user[4]
            return (user_id, full_name, role)
        return None


    # ТОВАРЫ

    def get_all_products(self):
        """Получение всех товаров с категориями, подкатегориями и остатками."""
        query = """
            SELECT 
                p.product_id,
                p.product_name,
                p.manufacturer,
                p.description,
                p.composition,
                p.price,
                p.image_path,
                cat.category_name,
                subcat.subcategory_name,
                COALESCE(SUM(si.quantity), 0) as total_quantity
            FROM products p
            LEFT JOIN category_subcategory cs ON p.category_subcategory_id = cs.category_subcategory_id
            LEFT JOIN categories cat ON cs.category_id = cat.category_id
            LEFT JOIN subcategories subcat ON cs.subcategory_id = subcat.subcategory_id
            LEFT JOIN stock_items si ON p.product_id = si.product_id
            GROUP BY p.product_id, p.product_name, p.manufacturer, p.description, 
                     p.composition, p.price, p.image_path, cat.category_name, subcat.subcategory_name
            ORDER BY p.product_id
        """
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def get_product_sizes(self, product_id):
        """Получение доступных размеров для конкретного товара."""
        query = """
            SELECT stock_item_id, size, quantity
            FROM stock_items
            WHERE product_id = %s AND quantity > 0
            ORDER BY size
        """
        self.cursor.execute(query, (product_id,))
        return self.cursor.fetchall()


    # КОРЗИНА И ЗАКАЗЫ

    def get_or_create_cart(self, user_id):
        """Получение ID корзины (заказа без даты) или её создание."""
        query = "SELECT order_id FROM orders WHERE user_id = %s AND order_date IS NULL"
        self.cursor.execute(query, (user_id,))
        result = self.cursor.fetchone()

        if result:
            return result[0]

        # Создаем новую корзину
        insert_query = "INSERT INTO orders (user_id, order_date) VALUES (%s, NULL) RETURNING order_id"
        self.cursor.execute(insert_query, (user_id,))
        self.connection.commit()
        return self.cursor.fetchone()[0]

    def add_to_cart(self, user_id, stock_item_id, quantity):
        """Добавление товара в корзину."""
        order_id = self.get_or_create_cart(user_id)

        # Проверяем, есть ли уже этот товар в корзине
        check_query = "SELECT order_item_id, quantity FROM order_items WHERE order_id = %s AND stock_item_id = %s"
        self.cursor.execute(check_query, (order_id, stock_item_id))
        result = self.cursor.fetchone()

        if result:
            # Обновляем количество
            new_qty = result[1] + quantity
            update_query = "UPDATE order_items SET quantity = %s WHERE order_item_id = %s"
            self.cursor.execute(update_query, (new_qty, result[0]))
        else:
            # Вставляем новую строку
            insert_query = "INSERT INTO order_items (order_id, stock_item_id, quantity) VALUES (%s, %s, %s)"
            self.cursor.execute(insert_query, (order_id, stock_item_id, quantity))

        self.connection.commit()
        return order_id

    def checkout_cart(self, user_id):
        """Оформление заказа (проставление текущей даты)."""
        query = """
            UPDATE orders 
            SET order_date = CURRENT_DATE 
            WHERE user_id = %s AND order_date IS NULL
            RETURNING order_id
        """
        self.cursor.execute(query, (user_id,))
        result = self.cursor.fetchone()
        self.connection.commit()
        return result[0] if result else None

    def get_cart_items(self, user_id):
        """Получение товаров в корзине (заказе без даты)."""
        query = """
            SELECT 
                oi.order_item_id,
                oi.quantity,
                si.size,
                p.product_name,
                p.price,
                p.image_path
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN stock_items si ON oi.stock_item_id = si.stock_item_id
            JOIN products p ON si.product_id = p.product_id
            WHERE o.user_id = %s AND o.order_date IS NULL
        """
        self.cursor.execute(query, (user_id,))
        return self.cursor.fetchall()


    # ПРОСМОТР ЗАКАЗОВ (для менеджера/админа)

    def get_all_orders(self):
        """Получение всех оформленных заказов."""
        query = """
            SELECT 
                o.order_id, 
                o.order_date, 
                u.last_name || ' ' || u.first_name || ' ' || COALESCE(u.middle_name, '') as client_name
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            WHERE o.order_date IS NOT NULL
            ORDER BY o.order_id DESC
        """
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def get_order_details(self, order_id):
        """Получение состава заказа (для окна просмотра)."""
        query = """
            SELECT 
                p.product_name,
                p.manufacturer,
                si.size,
                oi.quantity,
                p.price,
                (p.price * oi.quantity) as sum
            FROM order_items oi
            JOIN stock_items si ON oi.stock_item_id = si.stock_item_id
            JOIN products p ON si.product_id = p.product_id
            WHERE oi.order_id = %s
        """
        self.cursor.execute(query, (order_id,))
        return self.cursor.fetchall()

    def delete_order_item(self, order_item_id):
        """Удаление позиции из заказа."""
        query = "DELETE FROM order_items WHERE order_item_id = %s"
        self.cursor.execute(query, (order_item_id,))
        self.connection.commit()