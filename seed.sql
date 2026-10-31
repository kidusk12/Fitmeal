-- FitMeal starter data. Safe to run more than once.
-- EVERYTHING BELOW IS SAMPLE DATA: replace prices, recipes and the payment account with your real ones.

INSERT INTO settings (key, value, description) VALUES
    ('business_name',      'FitMeal', 'Name shown to customers'),
    ('payment_window_min', '10',      'Minutes a customer has to send a payment screenshot'),
    ('kitchen_review_min', '30',      'Minutes the kitchen has to approve or deny a payment'),
    ('alert_repeat_min',   '10',      'Minutes between kitchen reminders and overdue alerts'),
    ('delivery_fee_etb',   '50',      'Flat delivery fee in ETB (SAMPLE: set your real fee)'),
    ('daily_order_limit',  '100',     'Maximum orders per day'),
    ('opening_time',       '08:00',   'Kitchen opens (24h, Addis Ababa time)'),
    ('closing_time',       '21:00',   'Kitchen closes (24h, Addis Ababa time)')
ON CONFLICT (key) DO NOTHING;

INSERT INTO categories (name, sort_order) VALUES
    ('Breakfast', 1), ('Pre-workout', 2), ('Post-workout', 3), ('Shakes', 4), ('Drinks', 5)
ON CONFLICT (name) DO NOTHING;

INSERT INTO payment_accounts (label, account_number, holder_name, sort_order)
SELECT 'Telebirr', '09XXXXXXXX', 'REPLACE WITH ACCOUNT HOLDER NAME', 1
WHERE NOT EXISTS (SELECT 1 FROM payment_accounts);

INSERT INTO ingredients (name, unit, allergen) VALUES
    ('Oats', 'g', NULL),
    ('Banana', 'pcs', NULL),
    ('Whey protein', 'g', 'dairy'),
    ('Milk', 'ml', 'dairy'),
    ('Egg', 'pcs', 'egg'),
    ('Spinach', 'g', NULL),
    ('Avocado', 'g', NULL),
    ('Olive oil', 'ml', NULL),
    ('Chicken breast', 'g', NULL),
    ('Brown rice', 'g', NULL),
    ('Broccoli', 'g', NULL),
    ('Sweet potato', 'g', NULL),
    ('Whole wheat bread', 'g', 'gluten'),
    ('Peanut butter', 'g', 'peanut'),
    ('Honey', 'g', NULL),
    ('Greek yogurt', 'g', 'dairy'),
    ('Orange', 'pcs', NULL)
ON CONFLICT (name) DO NOTHING;

INSERT INTO meals (meal_code, name, category_id, price_etb, calories, protein_g, carbs_g, fat_g, description, recipe)
SELECT v.code, v.name, cat.id, v.price, v.kcal, v.p, v.carb, v.f, v.descr, v.recipe
FROM (VALUES
    ('M-001', 'Protein Oats Bowl', 'Breakfast', 150, 420, 28, 55, 10,
     'Warm oats with banana and whey protein.',
     'SAMPLE RECIPE: Cook oats in milk 5 min, stir in whey off the heat, top with sliced banana.'),
    ('M-002', 'Veggie Egg Scramble', 'Breakfast', 140, 350, 24, 12, 22,
     'Soft scrambled eggs with spinach and avocado.',
     'SAMPLE RECIPE: Wilt spinach in olive oil, add beaten eggs, scramble softly, serve with avocado.'),
    ('M-003', 'Chicken and Rice Power Bowl', 'Post-workout', 220, 620, 48, 70, 14,
     'Grilled chicken breast, brown rice and steamed broccoli.',
     'SAMPLE RECIPE: Grill seasoned chicken 6 min per side, steam broccoli, plate over cooked brown rice.'),
    ('M-004', 'Chicken and Sweet Potato Plate', 'Post-workout', 230, 580, 45, 62, 16,
     'Grilled chicken with roasted sweet potato and spinach.',
     'SAMPLE RECIPE: Roast cubed sweet potato 25 min at 200C, grill chicken, serve over wilted spinach.'),
    ('M-005', 'Banana Peanut Butter Toast', 'Pre-workout', 120, 380, 12, 52, 14,
     'Whole wheat toast with peanut butter, banana and honey.',
     'SAMPLE RECIPE: Toast bread, spread peanut butter, top with banana slices and a drizzle of honey.'),
    ('M-006', 'Greek Yogurt Parfait', 'Pre-workout', 130, 300, 20, 38, 6,
     'Greek yogurt layered with oats, banana and honey.',
     'SAMPLE RECIPE: Layer yogurt, oats and banana in a cup, finish with honey.'),
    ('M-007', 'Banana Protein Shake', 'Shakes', 110, 280, 30, 20, 8,
     'Whey, milk, banana and a spoon of peanut butter.',
     'SAMPLE RECIPE: Blend whey, milk, banana and peanut butter with ice for 40 seconds.'),
    ('M-008', 'Green Recovery Smoothie', 'Shakes', 100, 220, 15, 30, 5,
     'Spinach, banana, Greek yogurt and honey.',
     'SAMPLE RECIPE: Blend spinach, banana, yogurt, honey and ice until smooth.'),
    ('M-009', 'Fresh Orange Juice', 'Drinks', 60, 110, 2, 26, 0.5,
     'Freshly squeezed orange juice, no added sugar.',
     'SAMPLE RECIPE: Juice four oranges, strain if the customer prefers, serve cold.')
) AS v(code, name, cat, price, kcal, p, carb, f, descr, recipe)
JOIN categories cat ON cat.name = v.cat
ON CONFLICT (meal_code) DO NOTHING;

INSERT INTO meal_ingredients (meal_id, ingredient_id, quantity)
SELECT m.id, i.id, v.qty
FROM (VALUES
    ('M-001', 'Oats', 60), ('M-001', 'Banana', 1), ('M-001', 'Whey protein', 30), ('M-001', 'Milk', 200),
    ('M-002', 'Egg', 3), ('M-002', 'Spinach', 50), ('M-002', 'Avocado', 50), ('M-002', 'Olive oil', 5),
    ('M-003', 'Chicken breast', 150), ('M-003', 'Brown rice', 150), ('M-003', 'Broccoli', 100), ('M-003', 'Olive oil', 5),
    ('M-004', 'Chicken breast', 150), ('M-004', 'Sweet potato', 200), ('M-004', 'Spinach', 50), ('M-004', 'Olive oil', 5),
    ('M-005', 'Whole wheat bread', 60), ('M-005', 'Peanut butter', 30), ('M-005', 'Banana', 1), ('M-005', 'Honey', 10),
    ('M-006', 'Greek yogurt', 200), ('M-006', 'Oats', 30), ('M-006', 'Honey', 15), ('M-006', 'Banana', 1),
    ('M-007', 'Whey protein', 30), ('M-007', 'Milk', 250), ('M-007', 'Banana', 1), ('M-007', 'Peanut butter', 15),
    ('M-008', 'Spinach', 50), ('M-008', 'Banana', 1), ('M-008', 'Greek yogurt', 100), ('M-008', 'Honey', 10),
    ('M-009', 'Orange', 4)
) AS v(code, ing, qty)
JOIN meals m ON m.meal_code = v.code
JOIN ingredients i ON i.name = v.ing
ON CONFLICT (meal_id, ingredient_id) DO NOTHING;
