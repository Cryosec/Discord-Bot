/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}", // Make sure it scans your source files
  ],
  theme: {
    extend: {
       fontFamily: {
         // Optional: Add custom fonts if needed
         // sans: ['Inter', 'sans-serif'],
       },
    },
  },
  plugins: [],
}