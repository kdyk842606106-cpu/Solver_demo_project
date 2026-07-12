import axios from 'axios'

export const getHealth = () => axios.get('/health').then((res) => res.data)
